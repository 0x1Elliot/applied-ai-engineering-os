# Fieldwork

A personal, scheduled research feed. Each window has its own reading prompt and notebook. Published content and private notes live in object storage, outside this repository.

## Run the demo

Use Node 22 or later. From projects/fieldwork run `node --test worker.test.mjs` to exercise publication, retries, reads and notebook access. To build, copy hosting.example.json to .openai/hosting.json inside this folder (create .openai first), supply your own private Site identity, and run `node build.mjs`.

src/index.html contains the browser UI. src/worker.mjs implements the Worker endpoints. The hosted environment supplies BUCKET and authenticates requests at the owner-private Site boundary. Never expose the Worker directly on a public route. Notebook operations also require the authenticated visitor identity. Operational data and service credentials stay outside GitHub.

## Iteration

Propose small changes on a feature branch, include a reproducible test and request review. Publishing a hosted revision is a separate step after approval. Do not assume merging a GitHub PR deploys the Site.
