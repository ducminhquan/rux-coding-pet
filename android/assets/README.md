# Local audio assets

The Android face graphics are drawn in Java; no bitmap/sprite dependency is required.
`scenarios.json` and `voices.json` are generated from scripts/ at build time.

Voice WAV files are local dependencies and are intentionally not part of the source
export. Import files with `scripts/prepare_local_assets.py`, or provide PCM WAV
files with the names listed in scripts/voices.json, plus:

- voice-thuy-duyen-attention.wav — attention phrase
- voice-thuy-duyen-completed.wav — completion phrase

The default voice id is thuy-duyen. The five sample WAV files are used by the web
voice selector. Provide recordings/generated audio that you are entitled to use.
The installed app and existing working project keep their current audio files;
this export does not modify them.
