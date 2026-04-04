# CHANGELOG

<!-- version list -->

## v0.9.0 (2026-04-04)

### Bug Fixes

- Checkout branch name instead of SHA to avoid detached HEAD in release workflow
  ([`80d25d0`](https://github.com/DanSega1/Conductor-Engine/commit/80d25d07bd7afa4827d850993b9d4041afbbea25))

- **capability**: 🐛 Fix indentation for man_page method
  ([`910cb23`](https://github.com/DanSega1/Conductor-Engine/commit/910cb23e00a3dd324254553d217fbbd04b08ab10))

- **capability**: 🐛 Fix indentation for man_page method
  ([`4260438`](https://github.com/DanSega1/Conductor-Engine/commit/4260438ee3ecc396c0f20bed9f2dbb2da2ef423b))

- **docs**: ✨ Update command examples to use correct file paths
  ([`890f609`](https://github.com/DanSega1/Conductor-Engine/commit/890f6091cd27592cc742d2307491b9e03499e215))

- **docs**: 🐛 Update image source in README for correct banner display
  ([`19bed23`](https://github.com/DanSega1/Conductor-Engine/commit/19bed237fbe80c645491b621e00e156accb7af7a))

### Chores

- **ci**: ✨ Update CI and release workflows for improved actions and triggers
  ([`bda46b4`](https://github.com/DanSega1/Conductor-Engine/commit/bda46b41f835ddbe3dab1ca9d478f035e48ce45e))

- **ci**: 🔧 Update Python version to 3.14 in CI workflows
  ([`f766682`](https://github.com/DanSega1/Conductor-Engine/commit/f7666829fb83d16a10902bda3955c459d4c85fb3))

- **docs**: ✨ Update roadmap with README and Python 3.14 upgrade status
  ([`431e8d3`](https://github.com/DanSega1/Conductor-Engine/commit/431e8d372246361f12ed28a16366b7d32b2d3ac9))

- **gitignore**: ✨ Update .gitignore and MANIFEST.in for examples output
  ([`b26b6b3`](https://github.com/DanSega1/Conductor-Engine/commit/b26b6b3836e9558ab5607788a294f9e1aa2a6dcc))

- **roadmap**: ✨ Update roadmap with backlog and engineering tasks
  ([`7a131f8`](https://github.com/DanSega1/Conductor-Engine/commit/7a131f8c49c9dbd1cec5639e319bab25941fa111))

- **vscode**: ✨ Update VSCode settings for Python environment activation
  ([`99d4d61`](https://github.com/DanSega1/Conductor-Engine/commit/99d4d619184d4835a54a36894c838a92913174ff))

### Features

- **capability**: ✨ Add man_page method for optional CLI help output
  ([`04f5b40`](https://github.com/DanSega1/Conductor-Engine/commit/04f5b40990265b2ce419d94ec00da3586f5748b1))

- **cli**: ✨ Add help command with detailed topics and examples
  ([`31c620b`](https://github.com/DanSega1/Conductor-Engine/commit/31c620bb9f1cb84436b39770e33f9719b56f4ad1))

- **docs**: ✨ Add man page and update CLI help documentation
  ([`58fa884`](https://github.com/DanSega1/Conductor-Engine/commit/58fa8840a80c0c36b864f2c8c78df7180a1d393a))

- **docs**: ✨ Update README with CI badges and architecture overview
  ([`c0ebf85`](https://github.com/DanSega1/Conductor-Engine/commit/c0ebf853f3aa0158406a258b8b9e031031d693e6))

- **examples**: ✨ Add runnable examples for Conductor Engine tasks and workflows
  ([`f63a519`](https://github.com/DanSega1/Conductor-Engine/commit/f63a519c28cbb8a34826110f4eed847f0fc70fbe))

- **pyproject**: ✨ Add Python classifiers for PyPI badges
  ([`7888e18`](https://github.com/DanSega1/Conductor-Engine/commit/7888e18d2167fa30f2b4c24a320ea3b1acc98274))

- **tests**: ✨ Add regression tests for JSON-backed local task store
  ([`5704c28`](https://github.com/DanSega1/Conductor-Engine/commit/5704c28e3802a01ef7eaab07c640ff3dc87f142c))

- **tests**: ✨ Add tests for CLI help commands and packaging metadata
  ([`760879e`](https://github.com/DanSega1/Conductor-Engine/commit/760879eafc8d2bcb560a9913aae1fbd6a688c17f))


## v0.8.0 (2026-04-01)


## v0.7.0 (2026-04-01)

### Features

- **docs**: ✨ Add home-ai-control-plane use case and analysis to documentation
  ([`6b0e21a`](https://github.com/DanSega1/Conductor-Engine/commit/6b0e21a847a841796f786693ae9926cb159d03f0))

- **task**: ✨ Extend TaskStatus and add AuditEntry model
  ([`e2b207f`](https://github.com/DanSega1/Conductor-Engine/commit/e2b207ffaf3db9aafc40c9463011dd36ad98260c))


## v0.6.0 (2026-04-01)

### Features

- **cli**: ✨ Add version argument to CLI for displaying package version
  ([`f74ce25`](https://github.com/DanSega1/Conductor-Engine/commit/f74ce25626e2dab1c10012cdfa3d3966c74c7360))


## v0.5.0 (2026-04-01)


## v0.4.0 (2026-04-01)

### Features

- **workflow**: ✨ Add workflow interfaces and contracts
  ([`4b8bb2b`](https://github.com/DanSega1/Conductor-Engine/commit/4b8bb2bb4fcee8c4f3640e400fe40e3a4f1d198d))


## v0.3.0 (2026-03-31)


## v0.2.0 (2026-03-31)

### Features

- **cli**: 🎉 Enhance CLI with rich output and new commands
  ([`af9afcc`](https://github.com/DanSega1/Conductor-Engine/commit/af9afccd4af55106795bb9a38562e2347fa50218))

- **task**: 🎉 Add max_retries to TaskSubmission and TaskRecord
  ([`aed7ef1`](https://github.com/DanSega1/Conductor-Engine/commit/aed7ef15710b184c76e3af06b945fc40d4785cb6))

- **workflows**: 🎉 Add squad management workflows
  ([`20ddacf`](https://github.com/DanSega1/Conductor-Engine/commit/20ddacfe5fced9b128fb560b6ae15cf58611052f))


## v0.1.1 (2026-03-20)


## v0.1.0 (2026-03-20)

- Initial Release
