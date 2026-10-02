# Historical routing pilot: a negative result with narrow scope

## What was tested

A small historical local-inference pilot compared four routing arms on four
tasks, with two trials per task and arm: 32 requests total. Each arm returned
an accepted result on all eight requests. This ceiling left no room for the
pilot to distinguish output quality.

An offline routing replay took 306.97 seconds, compared with 240.89 seconds for
a fixed Flash route, a 27.4% increase. The replay excluded model-loading time.
In a four-run routine-task slice, the 35B configuration with thinking disabled
completed 0/4, while the thinking-enabled configuration completed 4/4.

## What the result supports

The pilot did not show a benefit for the tested router over the fixed route on
the measured replay. Its routine-task slice also showed that disabling thinking
could fail on that task, despite any expected speed benefit. These are useful
engineering signals for those exact observations; they do not rank models or
establish a general routing policy.

## Limits

The sample was tiny and reached an 8/8 ceiling on every arm. Task order and
blocking were potential confounds. The historical run did not preserve enough
provenance to reproduce it fully: the runner, exact runtime build, and model
weights were not all pinned together. The reported replay excludes loading, so
it is not an end-to-end cold-start comparison.

The current 40-case synthetic evaluator is a separate artifact. It does not
reproduce these timing or routing results, and its public answer key prevents
its held-out-designated cases from serving as a blind set. Do not combine the
pilot counts with the synthetic case scores or use either as a general model
ranking.

This summary preserves the measured counts and timing while omitting private
paths, model registry contents, request logs, and transcripts.
