# sounds/

The cockpit voice pack lives here — one `.mp3` per control (`gear_up.mp3`,
`jettison_alarm.mp3`, ...). Generate yours with your own crew names:

```bash
export ELEVENLABS_API_KEY=sk_...
python3 ../cockpit/generate_sounds.py
```

`install.sh` converts them to `.wav` on the Pi for low-latency playback.
Audio files are gitignored on purpose: if your lines use your kids' real
names, they should never end up in a public repo.
