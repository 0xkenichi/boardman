import { z } from "zod";

/** Which end of the ball a team defends — mirrors ../types/common.ts. */
export const SideSchema = z.enum(["home", "away"]);
