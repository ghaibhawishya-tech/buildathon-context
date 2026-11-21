# The editorial film

A 36-second Aftertone pitch for podcast editors and Product Space judges. The film follows one piece of tape from an hour of conversation through the decision to publish a short. Jessica’s selected ElevenLabs performance runs at its recorded speed. Two independent compositions share its timing. The landscape master is 1920 × 1080 and the portrait master is 1080 × 1920, both at 60 fps.

## Render

From the studio root with the dependencies in requirements.txt installed:

```sh
python motion/film.py exports/cinematic_video.mp4
python motion/film.py --portrait exports/aftertone_short.mp4
python motion/studio_cut.py
```

The third command runs the real studio ranking and export path and writes a 30-second captioned vertical MP4. Launch the studio and open Project brief to watch the masters.

## Storyboard

| Time | Direction | Movement and sound |
| --- | --- | --- |
| 0.00–5.79 | One hour into thirty seconds | Two reels rotate in opposite directions while registration marks travel along the tape. The display letters settle individually over Jessica’s opening. |
| 5.79–8.28 | Find the entry point | A scanning playhead crosses a waveform. The cream field cuts to ink. |
| 8.28–11.96 | Start too late | A coral splice carries the left trim bracket into the question. |
| 11.96–16.11 | End too soon | The right bracket cuts into the payoff against a dark field. |
| 16.11–18.93 | Hear the turn | A tonearm follows a rotating groove. The mint palette opens the solution section. |
| 18.93–23.55 | Choose the window | Paired edit brackets frame the voice track and a moving cursor measures the interval. |
| 23.55–26.04 | Inspect the evidence | Opening, turn and closing line slide into a three-line proof. |
| 26.04–28.89 | Make the editorial decision | Direction strips resolve to the final cut. |
| 28.89–31.53 | Remember the voice | The first draft, edited copy and next draft occupy the same typesetting grid. |
| 31.53–36.00 | Shape the next cut | The groove returns under the wordmark. A short end hold lets the sentence land. |

Each chapter change carries a quiet synthesized splice click. The soundtrack uses the selected performance and original generated cues. The timed narration script and word-level alignment are in script.json. Alignment was estimated from speech recognition matched against the supplied script.

## Customize

In film.py, SCENES controls headlines, object selection and palette. Canvas supplies shared type, line, shape and layout primitives. reel, ticks, art and caption handle animated objects and speech-following text. frame(t,w,h) renders a deterministic composition for any specific time. Use the two export dimensions when rendering finished media. A new narration needs matching word timings and chapter boundaries.

The type is Barlow Condensed Black, DM Serif Display Italic and IBM Plex Mono. Their OFL licenses are included in fonts. The visual reference was the way typography follows the underlying grid in Saul Bass’s North by Northwest sequence. All illustrations, motion and sound accents were created for Aftertone. [Title sequence reference](https://www.artofthetitle.com/title/north-by-northwest/)
