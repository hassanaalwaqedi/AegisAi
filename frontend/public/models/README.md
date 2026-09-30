# Aegis rigged operator asset contract

Place the production avatar at `aegis-operator.glb` in this directory. Until
that rig is supplied, the Intelligence route uses the approved operator artwork
with restrained state-driven motion. The artwork is an interim visual skin, not
the final skeletal animation system.

The runtime discovers clips case-insensitively. Supply these clips where
possible:

- `idle` / `breath`
- `listen` / `attention`
- `think` / `focus`
- `speak` / `talk`
- `present_left`, `present_right`
- `point_left`, `point_right`
- `summon_left`, `summon_right`
- `push_forward`
- `warning`

Name hand and torso bones with standard names such as `RightHand`, `LeftHand`,
`RightShoulder`, `LeftShoulder`, and `Chest` (Mixamo equivalents are detected).
The runtime projects those bones to attach DOM result surfaces to actual rig
positions.

Include a mouth blendshape named `jawOpen`, `mouthOpen`, or a conventional open
viseme (`viseme_aa`, `viseme_ah`, or `viseme_oh`). During real native PCM
playback, the Web Audio analyser drives that target; it is reset immediately
when playback drains. If TTS later provides viseme timestamps, they should take
precedence over this amplitude fallback.
