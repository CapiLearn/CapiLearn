# Credits and Attribution

## Purpose

This page documents external sources, datasets, course materials, models, libraries, and other third-party resources used in CapiLearn. All teammates should update this page when they add a new external dependency of any kind (see [Team Attribution Guidelines](#team-attribution-guidelines)).

---

## Course Content and Data Sources

### Full Stack Open

| Field | Details |
|---|---|
| **Source name** | Full Stack Open |
| **Repository** | https://github.com/fullstack-hy2020/fullstack-hy2020.github.io |
| **Course website** | https://fullstackopen.com/ |
| **Use in CapiLearn** | First course corpus used to test ingestion, chunking, vector storage, and retrieval during local RAG development |
| **License** | Creative Commons BY-NC-SA 3.0, per the source repository README |

The Full Stack Open material is used for development and evaluation purposes within the RAG pipeline. CapiLearn does not redistribute or republish this material.

---

## Project Relationship Disclaimer

CapiLearn is an independent educational project. It is not affiliated with, endorsed by, or sponsored by Full Stack Open or the University of Helsinki.

---

## RAG and ML Tooling

| Tool | Use in CapiLearn |
|---|---|
| **ChromaDB** | Local vector storage for course context chunks |
| **sentence-transformers** | Local text embedding library |
| **all-MiniLM-L6-v2** | Default embedding model for local retrieval experiments (`sentence-transformers/all-MiniLM-L6-v2`) |

---

## Team Attribution Guidelines

Update this page whenever you add any of the following to the project:

- Datasets or training data
- Course materials or educational content
- UI assets, icons, or illustrations
- Fonts
- Model checkpoints or fine-tuned weights
- Third-party APIs or external services
- External code examples, templates, or boilerplate

For each item, include at minimum: the source name, a link, the use in CapiLearn, and any applicable license information.

---

## Future Attribution Work

This page should grow as CapiLearn adds new course sources, models, and external integrations. If you integrate a new resource and are unsure whether it needs an entry here, err on the side of adding one.
