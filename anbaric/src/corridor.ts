import {readFileSync} from "node:fs";
import {dirname, join} from "node:path";
import {fileURLToPath} from "node:url";

export type Place = {id : string, name : string, regionId : string, lat : number, lon : number};
export type Note = {need : string, label : string, when : string, placeLabel : string, text : string};
export type Stage = {title : string, highway : string, distanceKm : number, from? : [number, number], to? : [number, number], path? : Array<[number, number]>};

type Segment = {fromId : string, toId : string, fromName : string, toName : string, highway : string, km : number, path? : Array<[number, number]>};
type Atlas = {
    regions : Array<{id : string, name : string}>,
    places : Array<Place>,
    segments : Array<Segment>,
    chat : Record<string, {title : string, notes : Array<Note>}>,
};

const atlas = JSON.parse(readFileSync(join(dirname(fileURLToPath(import.meta.url)), "atlas.json"), "utf8")) as Atlas;

const NEED_ORDER = ["road", "stay", "water", "resupply", "season", "border", "safety"];
const placesById = new Map(atlas.places.map((place) => [place.id, place]));

type Directed = {toId : string, km : number, stage : Stage};
const graph = new Map<string, Array<Directed>>();

const link = (fromId : string, edge : Directed) => {
    const edges = graph.get(fromId) ?? [];
    edges.push(edge);
    graph.set(fromId, edges);
};

const at = (placeId : string) : [number, number] | undefined => {
    const place = placesById.get(placeId);
    return place ? [place.lat, place.lon] : undefined;
};

for (const segment of atlas.segments) {
    link(segment.fromId, {
        toId: segment.toId,
        km: segment.km,
        stage: {title: `${segment.fromName} to ${segment.toName}`, highway: segment.highway, distanceKm: segment.km,
            from: at(segment.fromId), to: at(segment.toId), path: segment.path},
    });
    link(segment.toId, {
        toId: segment.fromId,
        km: segment.km,
        stage: {title: `${segment.toName} to ${segment.fromName}`, highway: segment.highway, distanceKm: segment.km,
            from: at(segment.toId), to: at(segment.fromId), path: segment.path?.slice().reverse()},
    });
}

// Everything the public map needs: towns, highway lines and every sample note.
export const mapData = () => ({
    places: atlas.places,
    segments: atlas.segments.flatMap((segment) => {
        const from = at(segment.fromId);
        const to = at(segment.toId);
        return from && to ? [{path: segment.path ?? [from, to], highway: segment.highway}] : [];
    }),
    notes: Object.values(atlas.chat).flatMap((region) => region.notes),
});

export const places = () => atlas.places.slice().sort((left, right) => left.name.localeCompare(right.name));

export const knownPlace = (placeId : string) => placesById.has(placeId);

export const placeName = (placeId : string) => placesById.get(placeId)?.name ?? placeId;

const regionTitle = (regionIds : Array<string>) => {
    const everyRegion = atlas.regions.map((region) => region.id);
    if (everyRegion.length === regionIds.length && everyRegion.every((regionId) => regionIds.includes(regionId)))
        return "Alaska to Vancouver";
    const names = regionIds.map((regionId) => atlas.regions.find((region) => region.id === regionId)?.name).filter((name) : name is string => Boolean(name));
    if (names.length <= 1) return names[0] ?? "This route";
    if (names.length === 2) return `${names[0]} and ${names[1]}`;
    return `${names.slice(0, -1).join(", ")}, and ${names.at(-1)}`;
};

const relatedNotes = (regionIds : Array<string>) => {
    const newest = new Map<string, Note>();
    for (const regionId of regionIds) {
        for (const note of atlas.chat[regionId]?.notes ?? []) {
            const current = newest.get(note.need);
            if (!current || note.when > current.when) newest.set(note.need, note);
        }
    }
    return NEED_ORDER.flatMap((need) => {
        const note = newest.get(need);
        return note ? [note] : [];
    });
};

export type AssembledRoute = {
    fromName : string,
    toName : string,
    distanceKm : number,
    stages : Array<Stage>,
    relatedTitle : string,
    relatedNotes : Array<Note>,
    outcome : "ready" | "same" | "unroutable",
};

export const assembleRoute = (startId : string, endId : string) : AssembledRoute => {
    const fromName = placeName(startId);
    const toName = placeName(endId);
    if (startId === endId) {
        const regionId = placesById.get(startId)?.regionId;
        const regions = regionId ? [regionId] : [];
        return {fromName, toName, distanceKm: 0, stages: [], relatedTitle: regionTitle(regions), relatedNotes: relatedNotes(regions), outcome: "same"};
    }
    const queue : Array<{distance : number, node : string, stages : Array<Stage>, regions : Array<string>}> = [
        {distance: 0, node: startId, stages: [], regions: placesById.get(startId)?.regionId ? [placesById.get(startId)!.regionId] : []},
    ];
    const seen = new Set<string>();
    while (queue.length > 0) {
        queue.sort((left, right) => left.distance - right.distance);
        const current = queue.shift()!;
        if (seen.has(current.node)) continue;
        seen.add(current.node);
        if (current.node === endId) {
            const distanceKm = Math.round(current.distance * 10) / 10;
            return {
                fromName,
                toName,
                distanceKm,
                stages: current.stages,
                relatedTitle: regionTitle(current.regions),
                relatedNotes: relatedNotes(current.regions),
                outcome: "ready",
            };
        }
        for (const edge of graph.get(current.node) ?? []) {
            if (seen.has(edge.toId)) continue;
            const regionId = placesById.get(edge.toId)?.regionId;
            const regions = regionId && !current.regions.includes(regionId) ? current.regions.concat(regionId) : current.regions;
            queue.push({distance: current.distance + edge.km, node: edge.toId, stages: current.stages.concat(edge.stage), regions});
        }
    }
    return {fromName, toName, distanceKm: 0, stages: [], relatedTitle: "", relatedNotes: [], outcome: "unroutable"};
};
