# Mars Water Search — frontend

A React + TypeScript research-demo frontend. Eduardo owns the simulation engine
and Wolfram integration. This project has **no live simulation or agent reasoning**.

## Run locally

Node.js 22+ and npm:

```sh
npm install
npm run dev
```

Open the local URL printed by Vite. Run experiment plays nine predefined rounds;
Step advances one round; Pause stops playback; Reset returns to identical priors.
Select an agent or Pool to change the displayed belief. Ground truth is only
supplied at the final frame and must be explicitly revealed by the presenter.

```sh
npm run lint
npm run typecheck
npm test
npm run build
```

## Connect Eduardo's backend

Implement `createBackendSimulationClient` in
`src/simulation/BackendSimulationClient.ts` to return a `SimulationClient`.
That file (and helpers under `src/simulation/`, if needed) maps Eduardo's payloads
to frontend domain types. Do not put transport calls into React components.

Then set `VITE_SIMULATION_MODE=backend` in a local `.env` and restart Vite.
The default is `demo`. The backend placeholder deliberately displays a connection
error until implemented; it never silently falls back to a demo.
Vite environment variables are public browser configuration, not secret storage.

See [the integration contract](docs/simulation-frontend-contract.md).

## Demo assumptions

- 50×50 grid, four agents, one deposit, 300 credits per agent, 1,000-credit prize.
- Fixed nine-round story; no WAIT. Move costs 2 per Manhattan unit, observe 15,
  drill 100, human 160, and joining 5. These are authored fixture values, not
  negotiated backend defaults or runtime simulation calculations.
- C's private expert advice in round 3 is shared on joining in round 4. C reaches
  zero budget in round 8 and retains eligibility for D's round-9 discovery.
- The full presenter view may show multiple agents' beliefs and activity. It is
  **not an agent observation endpoint** or a human-adviser interface.
- Belief rasters are deliberately coarse, hand-authored display swatches expanded
  to the grid. They demonstrate selection, not Bayesian updating or a calibrated
  spatial model. Payouts are supplied fixture values, displayed to two decimals.
- Human advice is scripted. There is no LLM, live adviser, or networking service.
- Maps use x increasing right and y increasing down; positions are zero-based.

The frontend renders evidence and eligibility supplied by its provider; it never
decides whether an agent joins, what it knows, or who deserves a payout.
