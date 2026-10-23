# Edits to make in the "Preski Daily Post" routine prompt (apply only after you approve v2)

1. STEP 2: add to the list of files fetched with `paths`: every file under `fonts/` (BigShouldersDisplay-700/800/900.ttf, Figtree-400/600/700.ttf). Save them into ~/post/fonts/ so the renderer can load them. If a font is missing the renderer falls back to Inter and still works.
2. STEP 5 (REEL): replace the scene rules with: "30-60 s. At least 70% of the runtime must be real video from clips/; use photos only as short inserts (dated proof, a physique beat), at most 3 still scenes. 8-14 scenes of 3-6 s each (these set the voiceover pacing; the renderer cuts each scene into 1.2-2.2 s shots itself). Never open and close on the same photo unless the loop is the point. Optional `focus` on a photo scene: upper, mid or wide."
3. STEP 5 (SLIDES): "Give every point/text slide its own photo when a suitable one exists (the renderer auto-fills one from the post's pool if you don't). Use the new `stat` slide for the one number that matters. Use `\"highlight\": \"last\"` on list slides so the answer row is red."
4. STEP 6: unchanged command. Read 6 frames of the reel and check pace (a cut at least every 2 s) and that no photo repeats back to back. If the renderer prints REEL WARNING, fix the scenes (more clips) and re-render, max 3 rounds.
5. STEP 7: publish also `daily/DATE/reel-poster.jpg` and `fonts/*.ttf` (once; they persist).
6. Photo picking: also follow brand-rules-additions.md (append its text to brand-rules.md on the artifact).
