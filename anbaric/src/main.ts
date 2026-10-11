import {createServer, IncomingMessage, ServerResponse} from "node:http";
import {Human, JobPersistenceFactory, QueueFactory, SystemActor, serializeJob} from "anbaric";
import type {Actor} from "anbaric";
import {places} from "./corridor.js";
import {routesMachine} from "./machine.js";
import {routePage} from "./page.js";

const persistence = JobPersistenceFactory.instance();
const queue = QueueFactory.instance();
const routes = routesMachine(persistence, queue);

const readJson = (request : IncomingMessage) : Promise<Record<string, unknown>> =>
    new Promise((resolve, reject) => {
        const chunks : Array<Buffer> = [];
        request.on("data", (chunk) => chunks.push(chunk));
        request.on("error", reject);
        request.on("end", () => {
            try { resolve(JSON.parse(Buffer.concat(chunks).toString() || "{}")); }
            catch (error) { reject(error); }
        });
    });

const rider = async (request : IncomingMessage) : Promise<Actor> => {
    try { return await Human.fromSession(request); }
    catch { return new Human("dev", "rider"); }
};

const send = (response : ServerResponse, status : number, body : unknown) => {
    response.writeHead(status, {"content-type": "application/json"});
    response.end(JSON.stringify(body));
};

const handle = async (request : IncomingMessage, response : ServerResponse) => {
    const url = new URL(request.url ?? "/", "http://localhost");

    if (request.method === "GET" && url.pathname === "/") {
        response.writeHead(200, {"content-type": "text/html; charset=utf-8"});
        response.end(routePage(places()));
        return;
    }

    if (request.method === "POST" && url.pathname === "/routes") {
        const body = await readJson(request);
        try {
            const job = await routes.startJob(new Map([
                ["startId", body.startId],
                ["endId", body.endId],
            ]), await rider(request));
            send(response, 201, serializeJob(job));
        } catch (error) {
            send(response, 400, {error: error instanceof Error ? error.message : "The route request was not accepted."});
        }
        return;
    }

    const match = url.pathname.match(/^\/routes\/([^/]+)$/);
    if (request.method === "GET" && match) {
        try {
            const job = await persistence.retrieve(decodeURIComponent(match[1]), SystemActor.actor);
            send(response, 200, serializeJob(job));
        } catch {
            send(response, 404, {error: "That route job is not here."});
        }
        return;
    }

    send(response, 404, {error: "Not found."});
};

const server = createServer((request, response) => {
    handle(request, response).catch((error) => {
        send(response, 500, {error: error instanceof Error ? error.message : "Internal error"});
    });
});

const port = Number(process.env.PORT ?? 3000);
server.listen(port, () => console.log(`pedalatlas listening on ${port}`));
