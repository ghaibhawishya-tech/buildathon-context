# Aftertone

## Your project

Independent podcast editors scrub entire interviews to find a short passage that makes sense to a stranger. A dramatic sentence often needs the line before it and the consequence after it. Aftertone ranks complete passages, explains the editorial signals, and remembers what a creator changes.

Team Context · Product Space Agentic AI Hackathon · Problem 01, Media: content repurposing studio with brand memory.

## Build plan

1. Ingest source media with timed English/Hindi captions or optional Sarvam transcription. Find non-overlapping editorial moments and keep their evidence attached.
2. Give each creator a review desk with playable vertical exports, timed captions, platform copy and learned voice preferences.
3. Schedule approved clips, measure retention, re-rank subsequent episodes and package a downloadable studio.

The design draws on [Sharkyclips](https://github.com/utkualsir/sharkyclips) for the export-to-publishing workflow, [auto-video-editor](https://github.com/kiy0ni/auto-video-editor) for highlight scoring, [Chopify](https://github.com/mehbul/chopify) for the browser and subtitle workflow, and [stream-clipper](https://github.com/sidgaikwad/stream-clipper) for temporal peak selection. The implementation here is original. REA inspection covered AutoClip’s public web client. Its server-side ranking is private.
