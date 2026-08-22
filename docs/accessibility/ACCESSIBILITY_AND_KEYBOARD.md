# Aperture accessibility and keyboard guide

Aperture 0.17.7 improves keyboard and assistive-technology support without introducing the Version 2 visual redesign.

## Keyboard access

Use `Tab` and `Shift+Tab` to move between controls. Press `Ctrl+/` to open the keyboard-shortcut reference. Core commands include `Ctrl+I` for import, `Ctrl+Shift+B` for backup, and `Ctrl+Shift+R` for restore.

## Focus and accessible names

Interactive buttons receive a strong keyboard-focus policy. Controls with visible text receive a conservative accessible name when a workspace has not supplied a more specific one. Explicit workspace names always take precedence.

## Display scaling

Aperture relies on Qt high-DPI behavior and avoids fixed text sizes in the new accessibility components. Final Windows QA should cover 100%, 150%, 175%, and 200% display scaling.

## Version boundary

This release is a Version 1 accessibility and consistency increment. The Natuurgids.org Design System and major visual/navigation changes remain reserved for Version 2.

## AI Review keyboard shortcuts

| Key | Action |
|---|---|
| `J` | Move to the next suggestion |
| `K` | Move to the previous suggestion |
| `A` | Accept the selected suggestion |
| `Shift+Enter` | Accept the selected suggestion and continue |
| `R` | Reject the selected suggestion |
| `D` | Defer the selected suggestion |
| `O` | Open observation history |
| `Ctrl+Z` | Reverse the last acceptance |
| `F1` | Open help for the current screen |

The AI Review workspace also displays these keys at the bottom of the screen. Open **Help → Keyboard Shortcuts…** for the complete in-application reference.


## Viewer

| Key | Action |
|---|---|
| Left or Page Up | Previous image |
| Right or Page Down | Next image |
| Home | First image |
| End | Last image |
| F | Fit image |
| 1 | Actual size |
| + | Zoom in |
| - | Zoom out |

## Library inspector

| Key | Action |
|---|---|
| Ctrl+S | Save metadata changes |
| Esc | Discard pending metadata changes |
