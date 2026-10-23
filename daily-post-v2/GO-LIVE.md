# Daily Post v2: what changed and how to switch it on

Preview (separate page, your live one is untouched): https://claude.ai/artifact/Qrc6FEq3UKdH1hth8LdnWp
Rebuilt from the real 21 Oct post, so you can compare it with the old page.

## What was wrong, and the fix
| Problem you saw | Cause found | Fix in v2 |
|---|---|---|
| Reel slow and repetitive | 8 of 10 scenes were single still photos held 3.5-6 s with one slow zoom; only 2 real clips; the cover photo was reused as the end card | Every scene is cut into 1.2-2.2 s shots: clip scenes become several cuts from different parts of the clip, photo scenes become quick punch-ins. The renderer warns when more than 40% of the reel is stills |
| Reel "has no videos" | The cloud clip bank has 19 short clips, mostly gym throwbacks and travel | `bank_export.py` (menu 14 on the laptop) exports your best tagged portrait clips and sharper photos for the bank |
| Photo quality | Photos were exported small (about 900-1200 px) and drawn as-is; some picks were mirror selfies | Render copies are upscaled with LANCZOS, gently contrast-normalised and sharpened (originals never touched, bodies never retouched). New picking rules in brand-rules-additions.md |
| Slides plain, big empty areas | Text-only navy slides, default fonts | New design system: Big Shoulders Display + Figtree, progress ticks, split photo/text layouts (auto-filled so no slide is text only), a red answer row on lists, a new "stat" slide, auto-fit text |
| Page layout | Desktop-style three-column page | Phone-first page: reel first, swipeable carousel with dots, Story, caption with copy button, voiceover script, today's schedule, earlier posts |

## To switch the live Daily Post to v2 (needs your yes)
1. Publish `render_post.py` as `render_post.py.txt` on the live artifact (keep the old one as `render_post.v1.py.txt`), plus `fonts/*.ttf`.
2. Update the Preski Daily Post routine prompt with `ROUTINE-PROMPT-PATCH.md` (fetch fonts, new reel rules, publish `reel-poster.jpg`).
3. Next 08:59 run produces the new look. If anything fails, the routine can fall back to `render_post.v1.py.txt`.

## Better footage (the biggest lever)
On the laptop, after tagging: `preski-menu.cmd` option 14 writes `<lib>\bank` (clips + photos + clips.json/photos.json). Then in a Local Claude session: "publish the bank to the Daily Post artifact". Until real video is in the bank, the reel can only be as good as 19 clips allow.
