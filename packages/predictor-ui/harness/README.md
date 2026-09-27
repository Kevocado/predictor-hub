# Explainer panel — screenshot harness

Not a site. A review instrument: it renders every state the panel can be in,
from the same components and the same tokens the five Predictor sites use, so
what a screenshot shows is what ships.

```sh
npm install          # its own node_modules, on purpose
npm run build        # -> dist/
npm run preview      # http://localhost:4180
```

- `index.html` — every state, one after another
- `narrow.html` — the same page in a **390px** iframe. Headless Chrome on macOS
  will not open a window narrower than 500px, so the phone width is measured
  inside a frame rather than by resizing. Same origin, or the frame is
  cross-origin and unreadable.

## Why it has its own dependencies

`resolve.dedupe` points React at one instance, but the deeper reason is that
adding a build tool to `predictor-ui`'s own `package.json` can disturb the
library's test run — which it did, on the first attempt, silently breaking six
test files. A review instrument must not be able to break the thing it reviews.

## What it caught that tests could not

The record strip was gated on the v1 branch, so **every v2 panel silently
dropped its record** while 148 tests passed — because the component test rendered
`RecordStrip` directly and never through the panel. A screenshot is the only
instrument that reads the panel the way a reader does.
