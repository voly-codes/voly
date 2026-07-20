/**
 * voly-capability — CF Worker for executor capability profiles and routing.
 *
 * Endpoints:
 *   GET  /health
 *   POST /roles/sync
 *   POST /profiles/seed
 *   POST /profiles/evidence
 *   POST /match
 *   GET  /profiles/:id
 *   GET  /leaderboard/:category
 */

import { Hono } from "hono";
import { cors } from "hono/cors";
import { leaderboardRoutes } from "./routes/leaderboard";
import { matchRoutes } from "./routes/match";
import { profilesRoutes } from "./routes/profiles";
import { rolesRoutes } from "./routes/roles";
import type { AppBindings } from "./types";

const app = new Hono<AppBindings>();

app.use("*", cors());

app.get("/health", (c) =>
  c.json({ ok: true, service: "voly-capability" }),
);

app.route("/roles", rolesRoutes);
app.route("/profiles", profilesRoutes);
app.route("/match", matchRoutes);
app.route("/leaderboard", leaderboardRoutes);

export default app;
export type { Env } from "./types";
