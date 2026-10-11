import {Action, Code, JobPersistence, PropertyDefinition, Queue, State, StateMachine, Transition} from "anbaric";
import {assembleRoute, knownPlace} from "./corridor.js";
import {moderatorReview, reviewBrief, RISK_THRESHOLD, scoreRisk, writeBrief} from "./agents.js";

const text = (value : unknown) => typeof value === "string";

const startId = new PropertyDefinition("startId");
startId.required = true;
startId.example = "fairbanks";
startId.validation = (value) => text(value) && knownPlace(value);

const endId = new PropertyDefinition("endId");
endId.required = true;
endId.example = "whitehorse";
endId.validation = (value) => text(value) && knownPlace(value);

const fromName = new PropertyDefinition("fromName");
fromName.validation = text;

const toName = new PropertyDefinition("toName");
toName.validation = text;

const distanceKm = new PropertyDefinition("distanceKm");
distanceKm.validation = (value) => typeof value === "number" && value >= 0;

const stages = new PropertyDefinition("stages");
stages.validation = Array.isArray;

const relatedTitle = new PropertyDefinition("relatedTitle");
relatedTitle.validation = text;

const relatedNotes = new PropertyDefinition("relatedNotes");
relatedNotes.validation = Array.isArray;

const outcome = new PropertyDefinition("outcome");
outcome.validation = (value) => value === "ready" || value === "same" || value === "unroutable";

const language = new PropertyDefinition("language");
language.validation = text;

const brief = new PropertyDefinition("brief");
brief.validation = text;

const briefLanguage = new PropertyDefinition("briefLanguage");
briefLanguage.validation = text;

const riskScore = new PropertyDefinition("riskScore");
riskScore.validation = (value) => typeof value === "number" && value >= 0 && value <= 1;

const riskReason = new PropertyDefinition("riskReason");
riskReason.validation = text;

const reviewRecommendation = new PropertyDefinition("reviewRecommendation");
reviewRecommendation.validation = text;

const reviewNote = new PropertyDefinition("reviewNote");
reviewNote.validation = text;

const reviewRevision = new PropertyDefinition("reviewRevision");
reviewRevision.validation = text;

const approved = new PropertyDefinition("approved");
approved.validation = (value) => typeof value === "boolean";

const reviewedBy = new PropertyDefinition("reviewedBy");
reviewedBy.validation = text;

const trace = new PropertyDefinition("trace");
trace.validation = Array.isArray;

const assemble = new Action("Assemble schematic route", new Code("route-planner"),
    "Connects the named towns and attaches the published chat notes for the regions the line crosses");
assemble.run = async (job) => {
    const planned = assembleRoute(await job.properties.get("startId"), await job.properties.get("endId"));
    return new Map<string, unknown>([
        ["fromName", planned.fromName],
        ["toName", planned.toName],
        ["distanceKm", planned.distanceKm],
        ["stages", planned.stages],
        ["relatedTitle", planned.relatedTitle],
        ["relatedNotes", planned.relatedNotes],
        ["outcome", planned.outcome],
    ]);
};

const finished = async (job : {properties : {get : (key : string) => Promise<unknown>}}, expected : string) =>
    await job.properties.get("outcome") === expected;

export const routesMachine = (persistence : JobPersistence, queue : Queue) => new StateMachine(
    "routes",
    [
        new State("requested", [assemble], [
            new Transition("assembled", async (job) => await finished(job, "ready") || await finished(job, "same")),
            new Transition("unroutable", async (job) => await finished(job, "unroutable")),
        ]),
        // Claude Haiku writes the brief.
        new State("assembled", [writeBrief], [
            new Transition("briefed", async (job) => await job.properties.has("brief")),
        ]),
        // Jev decides whether a person must see it first.
        new State("briefed", [scoreRisk], [
            new Transition("flagged", async (job) => Number(await job.properties.get("riskScore")) >= RISK_THRESHOLD),
            new Transition("ready", async (job) => await job.properties.has("riskScore")),
        ]),
        // Claude Opus reviews only what Jev flagged, and advises the human.
        new State("flagged", [reviewBrief], [
            // Opus approves a safety flag: publish without waiting (ADR-005).
            // Border and legal advice always waits for a person.
            new Transition("ready", async (job) =>
                await job.properties.get("reviewRecommendation") === "approve"
                && await job.properties.get("riskReason") !== "border"),
            new Transition("review", async (job) => await job.properties.has("reviewNote")),
        ]),
        // A human approves or withholds it.
        new State("review", [moderatorReview], [
            new Transition("ready", async (job) => await job.properties.get("approved") === true),
            new Transition("withheld", async (job) => await job.properties.get("approved") === false),
        ]),
        new State("ready"),
        new State("withheld"),
        new State("unroutable"),
    ],
    "requested",
    [startId, endId, fromName, toName, distanceKm, stages, relatedTitle, relatedNotes, outcome,
        language, brief, briefLanguage, riskScore, riskReason, reviewRecommendation, reviewNote, reviewRevision, approved, reviewedBy, trace],
    persistence,
    queue,
);
