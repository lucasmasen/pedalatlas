import {Action, Code, JobPersistence, PropertyDefinition, Queue, State, StateMachine, Transition} from "anbaric";
import {assembleRoute, knownPlace} from "./corridor.js";

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
            new Transition("ready", async (job) => await finished(job, "ready") || await finished(job, "same")),
            new Transition("unroutable", async (job) => await finished(job, "unroutable")),
        ]),
        new State("ready"),
        new State("unroutable"),
    ],
    "requested",
    [startId, endId, fromName, toName, distanceKm, stages, relatedTitle, relatedNotes, outcome],
    persistence,
    queue,
);
