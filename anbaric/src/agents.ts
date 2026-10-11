import {Action, Agent, AnthropicClient, Await, SecretStoreFactory, SystemActor} from "anbaric";
import type {AgentRequest, Job} from "anbaric";

// Each step is done by the model that is good at it, and every step is an
// Anbaric actor, so the job's audit trail names who did what:
//   Claude Haiku 5.5  writes the stage brief in the rider's language (cheap, fast writer)
//   Jev               scores safety and border risk as probabilities (a decision model, not a writer)
//   A human           approves any brief Jev flags before riders see it
// Only the public snapshot (route stages and published notes) reaches a model.
// Private WhatsApp drafts never do.

export type TraceStep = {
    step : string,
    actor : string,
    model : string,
    ms : number,
    inputTokens : number,
    outputTokens : number,
    costUsd : number,
    note : string,
};

const HAIKU = "claude-haiku-5-5";
// Standard API pricing, USD per million tokens (prompts under 100K).
const HAIKU_PRICE = {input: 0.10, output: 0.50};
const JEV_URL = process.env.JEV_API_URL ?? "https://ai-gateway.vercel.sh/v1/evaluate";
const JEV_MODEL = process.env.JEV_MODEL ?? "typesafe-ai/jev";
export const RISK_THRESHOLD = 0.5;

// Keys come from Anbaric's secret store. Deployed, set them with
// `anbaric secrets set anthropic-api-key` and `anbaric secrets set ai-gateway-api-key`.
// Locally the store falls back to ANTHROPIC_API_KEY and AI_GATEWAY_API_KEY in the shell.
const secrets = SecretStoreFactory.instance();
const secret = async (name : string) : Promise<string> => {
    try { return (await secrets.retrieve(name, SystemActor.actor)) ?? ""; }
    catch { return ""; }
};
const anthropicKey = () => secret("anthropic-api-key");
const jevKey = () => secret("ai-gateway-api-key");

const traceOf = async (job : Job) : Promise<Array<TraceStep>> =>
    ((await job.properties.get("trace")) as Array<TraceStep> | undefined) ?? [];

type Note = {label : string, placeLabel : string, when : string, text : string};
type StageView = {title : string, highway : string, distanceKm : number};

const notesOf = async (job : Job) => ((await job.properties.get("relatedNotes")) as Array<Note> | undefined) ?? [];
const stagesOf = async (job : Job) => ((await job.properties.get("stages")) as Array<StageView> | undefined) ?? [];

// ---------- Claude Haiku: the writer ----------

class MeteredClient extends Agent.Client {
    last = {inputTokens: 0, outputTokens: 0};
    async generate(request : AgentRequest) {
        const inner = new AnthropicClient(
            {apiKey: await anthropicKey(), model: HAIKU, maxTokens: 4096},
            async (url, init) => {
                const response = await fetch(url, init);
                const usage = (await response.clone().json().catch(() => ({})))?.usage ?? {};
                this.last = {inputTokens: usage.input_tokens ?? 0, outputTokens: usage.output_tokens ?? 0};
                return response;
            },
        );
        return inner.generate(request);
    }
}

const haikuClient = new MeteredClient();
export const briefer = new Agent("claude-haiku-briefer", "writer", haikuClient);

const BRIEF_SCHEMA = {
    type: "object",
    properties: {
        brief: {type: "string", description: "Three to six short sentences for a cyclist riding this route."},
        briefLanguage: {type: "string"},
    },
    required: ["brief", "briefLanguage"],
    additionalProperties: false,
};

const briefPrompt = (language : string, stages : Array<StageView>, notes : Array<Note>) => [
    {
        role: "system" as const,
        content: [
            "You write short route briefs for long-distance touring cyclists.",
            `Write in ${language}. Translate the notes; do not quote them in another language.`,
            "Use only the stages and notes given. Notes are rider accounts, not checked facts: say 'riders report' and keep each note's date.",
            "Lead with anything about borders, safety, water or where camping is not allowed. If there are no notes, say so plainly.",
            "Never invent towns, distances, rules or services.",
        ].join(" "),
    },
    {
        role: "user" as const,
        content: JSON.stringify({stages, notes}),
    },
];

const fallbackBrief = (stages : Array<StageView>, notes : Array<Note>) => {
    const km = stages.reduce((total, stage) => total + stage.distanceKm, 0);
    const lines = [`${stages.length} stages, about ${Math.round(km)} km.`];
    for (const note of notes) lines.push(`Riders report (${note.label}, ${note.when}): ${note.text}`);
    if (!notes.length) lines.push("No published rider notes cover this route yet.");
    return lines.join(" ");
};

export const writeBrief = new Action("Write the rider brief", briefer,
    "Claude Haiku turns the stages and published notes into a short brief in the rider's language");
writeBrief.run = async (job) => {
    const language = ((await job.properties.get("language")) as string | undefined) || "English";
    const stages = await stagesOf(job);
    const notes = await notesOf(job);
    const started = Date.now();
    let brief = "";
    let briefLanguage = language;
    let step! : TraceStep;
    let failure = "";
    if (await anthropicKey()) {
        try {
            const out = await haikuClient.generate({messages: briefPrompt(language, stages, notes), outputSchema: BRIEF_SCHEMA});
            brief = String(out.brief ?? "");
            briefLanguage = String(out.briefLanguage ?? language);
            const {inputTokens, outputTokens} = haikuClient.last;
            step = {
                step: "Write the rider brief", actor: briefer.id, model: HAIKU, ms: Date.now() - started,
                inputTokens, outputTokens,
                costUsd: (inputTokens * HAIKU_PRICE.input + outputTokens * HAIKU_PRICE.output) / 1_000_000,
                note: "Cheap, fast writer: one short brief per route, translated",
            };
        } catch (error) {
            failure = error instanceof Error ? error.message : "The Claude call failed";
        }
    }
    if (failure) {
        brief = fallbackBrief(stages, notes);
        step = {
            step: "Write the rider brief", actor: briefer.id, model: "offline fallback (Claude call failed)",
            ms: Date.now() - started, inputTokens: 0, outputTokens: 0, costUsd: 0,
            note: failure,
        };
    } else if (!(await anthropicKey())) {
        brief = fallbackBrief(stages, notes);
        step = {
            step: "Write the rider brief", actor: briefer.id, model: "offline fallback (set the anthropic-api-key secret)",
            ms: Date.now() - started, inputTokens: 0, outputTokens: 0, costUsd: 0,
            note: "No key, so the published notes are listed as they are",
        };
    }
    return new Map<string, unknown>([
        ["brief", brief],
        ["briefLanguage", briefLanguage],
        ["trace", [...await traceOf(job), step]],
    ]);
};

// ---------- Jev: the decider ----------

type JevAnswers = {safety : number, border : number};

const probability = (answer : any) : number => {
    const value = answer?.probability ?? answer?.noul ?? answer?.p ?? answer?.value;
    return typeof value === "number" ? Math.max(0, Math.min(1, value)) : 0;
};

const askJev = async (state : string, key : string) : Promise<JevAnswers> => {
    const response = await fetch(JEV_URL, {
        method: "POST",
        headers: {"content-type": "application/json", "authorization": `Bearer ${key}`},
        body: JSON.stringify({
            model: JEV_MODEL,
            state,
            questions: {
                safety: {type: "boolean", instruction: "Could acting on this brief put a cyclist at physical risk if it is wrong or out of date?"},
                border: {type: "boolean", instruction: "Does this brief tell a rider what to do about a border, visa, customs or a legal rule?"},
            },
        }),
    });
    if (!response.ok) throw new Error(`Jev returned ${response.status}`);
    const body = await response.json();
    const answers = body.answers ?? body.result?.answers ?? {};
    return {safety: probability(answers.safety), border: probability(answers.border)};
};

// Offline stand-in so the demo still runs without a key. It reads the note
// categories the snapshot already carries; it is labelled as a fallback in the trace.
const offlineRisk = (notes : Array<Note>) : JevAnswers => ({
    safety: notes.some((note) => /safety|road/i.test(note.label)) ? 0.7 : 0.1,
    border: notes.some((note) => /border/i.test(note.label)) ? 0.9 : 0.05,
});

const decider = new Agent("jev-risk-scorer", "decider", new (class extends Agent.Client {
    async generate() { return {}; }
})());

export const scoreRisk = new Action("Score safety and border risk", decider,
    "Jev returns calibrated probabilities that the brief is safety-critical or gives border advice");
scoreRisk.run = async (job) => {
    const brief = String((await job.properties.get("brief")) ?? "");
    const notes = await notesOf(job);
    const started = Date.now();
    let answers : JevAnswers;
    let model = JEV_MODEL;
    let note = "Decision model: probabilities, not prose, so the threshold is a number we can tune";
    const key = await jevKey();
    if (key) {
        try {
            answers = await askJev(brief, key);
        } catch (error) {
            answers = offlineRisk(notes);
            model = "offline fallback (Jev call failed)";
            note = error instanceof Error ? error.message : "Jev call failed";
        }
    } else {
        answers = offlineRisk(notes);
        model = "offline fallback (set the ai-gateway-api-key secret)";
        note = "No key, so the published note categories stand in for Jev";
    }
    const riskScore = Math.max(answers.safety, answers.border);
    const riskReason = answers.border >= answers.safety ? "border" : "safety";
    const step : TraceStep = {
        step: "Score safety and border risk", actor: decider.id, model, ms: Date.now() - started,
        inputTokens: 0, outputTokens: 0, costUsd: 0,
        note: `${note}. safety ${answers.safety.toFixed(2)}, border ${answers.border.toFixed(2)}`,
    };
    return new Map<string, unknown>([
        ["riskScore", riskScore],
        ["riskReason", riskReason],
        ["trace", [...await traceOf(job), step]],
    ]);
};

// ---------- A human: the approver ----------

export const moderatorReview = new Await("Moderator approves the brief", "HUMAN",
    "Jev flagged this brief as safety-critical or border advice, so a person signs off before riders see it");
moderatorReview.fields = ["approved"];
moderatorReview.resolveUrl = (job) => `/?review=${encodeURIComponent(job.id)}`;
