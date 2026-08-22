# Background thumbnails and responsiveness

Fieldora treats thumbnails as derivatives, never as a reason to block research
work. The Photos screen displays placeholders immediately and submits missing
derivatives to the durable background job engine.

## What the status means

The bottom bar can show:

- **checking** — lightweight reads are checking whether generated files exist;
- **queued** — visible cache checks are waiting for a worker;
- **awaiting background generation** — originals are being handled by durable
  jobs and the screen will check again; or
- **ready** — all currently loaded assets have thumbnails.

Thumbnail generation may continue for minutes for large or remote originals.
You can immediately open another Fieldora screen. Leaving Photos clears
speculative gallery checks but does not cancel durable generation. Returning to
Photos checks the cache every five seconds and fills completed thumbnails.

## Responsiveness contract

The GUI never decodes an original photograph or writes a derivative. Those
operations run outside the Qt event thread. Screen navigation and an active
placeholder-driven workspace must complete within three seconds even when
thumbnail jobs remain queued.
