# Music Renamer - Development Context

This document provides comprehensive context for developers working on this project. It's designed to help AI assistants and human developers quickly understand the codebase structure, patterns, and conventions.

---

## Project Overview

**Music Renamer** is a LAN-only web application for batch renaming audio files. It provides a web UI for scanning, editing metadata, and renaming files in-place without modifying embedded tags.

### Core Philosophy
- **No database**: All operations are stateless and file-based
- **In-place operations**: Files are renamed in their original directory
- **Manual control**: User explicitly selects which files to process
- **Safety first**: Confirmations, collision detection, and detailed reporting

---

## Technology Stack

### Backend
- **Python 3.12+**
- **Flask 3.0.2**: Web framework
- **Gunicorn 21.2.0**: WSGI server for production
- **Mutagen 1.47.0**: Audio metadata reading (fallback only)

### Frontend
- **Vanilla JavaScript**: No frameworks, pure ES6+
- **HTML5 + CSS3**: Modern, responsive design
- **Dark mode support**: Via CSS `prefers-color-scheme`

### Deployment
- **Docker**: Containerized deployment
- **Docker Compose**: Orchestration

---

## Project Structure

```
.
├── app/
│   ├── app.py                 # Flask backend (main application)
│   └── templates/
│       └── index.html         # Single-page UI (HTML + CSS + JS)
├── docker/
│   ├── Dockerfile             # Container image definition
│   └── entrypoint.sh          # Container startup script
├── beets/                     # (Optional) Beets integration
├── .github/                   # GitHub workflows
├── .vscode/                   # VS Code settings
├── compose.yaml               # Docker Compose configuration
├── requirements.txt           # Python dependencies
├── README (1).md              # Main documentation
└── CONTEXT.md                 # This file
```

---

## Key Files Deep Dive

### `app/app.py` (Backend)
**Purpose**: Flask API server handling all backend operations

**Key Functions**:
- `parse_artist_title_from_filename()`: Extracts metadata from filename using heuristics
- `sanitize_filename()`: Removes forbidden filesystem characters
- `scan_folder()`: Recursively scans for audio files
- `build_rename_plan()`: Generates rename operations with collision detection
- `apply_renames()`: Executes file renames with conflict resolution

**API Endpoints**:
- `GET /api/settings`: Returns rename template configuration
- `POST /api/scan`: Scans inbox folder and returns file list
- `POST /api/preview`: Previews rename operations
- `POST /api/apply`: Executes rename operations
- `POST /api/delete`: Deletes specified files

**Important Patterns**:
- All endpoints return JSON (even errors)
- File operations use `os.replace()` for atomic renames
- Collision resolution appends `(1)`, `(2)`, etc.
- Filename parsing prioritizes filename over embedded tags

### `app/templates/index.html` (Frontend)
**Purpose**: Single-page application with embedded CSS and JavaScript

**Architecture**:
```
HTML Structure
├── Toolbar (buttons + search)
├── Filter Stats
├── Items Table
│   ├── Checkbox column
│   ├── File path
│   ├── Artist (editable)
│   ├── Title (editable)
│   ├── Extension
│   ├── Date/Time (sortable)
│   └── Preview name (live)
└── Output (JSON response display)
```

**JavaScript State Management**:
- `CURRENT_ITEMS`: All scanned files (master list)
- `FILTERED_ITEMS`: Currently visible files after search filter
- `SEARCH_TERM`: Current search query
- `SORT_DESC`: Sort direction for date/time
- `RENAME_TEMPLATE`: Filename template from server

**Key JavaScript Functions**:
- `scan()`: Fetches file list from server
- `filterItems()`: Applies search filter to items
- `renderItems()`: Renders table rows with event listeners
- `buildPreviewName()`: Client-side preview generation
- `deleteSelected()`: Deletes selected files with confirmations
- `toggleSortByDate()`: Toggles date/time sorting
- `syncHeaderChk()`: Syncs "select all" checkbox state

**Event Flow**:
1. User action (click, input, etc.)
2. Update `CURRENT_ITEMS` state
3. Apply filter → `FILTERED_ITEMS`
4. Re-render table
5. Attach event listeners to new DOM elements

---

## Data Flow

### Scan Operation
```
User clicks "Scan"
    ↓
Frontend: POST /api/scan
    ↓
Backend: Scan /inbox recursively
    ↓
Backend: Parse filename → Artist/Title
    ↓
Backend: Fallback to tags if parsing failed
    ↓
Backend: Return items with metadata
    ↓
Frontend: Store in CURRENT_ITEMS
    ↓
Frontend: Apply filter → FILTERED_ITEMS
    ↓
Frontend: Render table
```

### Rename Operation
```
User edits Artist/Title in table
    ↓
Frontend: Update CURRENT_ITEMS[i].artist/title
    ↓
Frontend: Live update preview column
    ↓
User clicks "Preview rename"
    ↓
Frontend: POST /api/preview with CURRENT_ITEMS
    ↓
Backend: Generate rename plan
    ↓
Backend: Check for collisions
    ↓
Backend: Return preview with collision flags
    ↓
User clicks "Apply rename"
    ↓
Frontend: POST /api/apply with CURRENT_ITEMS
    ↓
Backend: Execute renames with conflict resolution
    ↓
Backend: Return moved/skipped/failed lists
    ↓
Frontend: Display results
    ↓
Frontend: Auto-scan to refresh
```

### Delete Operation
```
User selects files via checkboxes
    ↓
User clicks "Delete selected"
    ↓
Frontend: Filter CURRENT_ITEMS for selected=true
    ↓
Frontend: For each selected file:
    ├─ Show confirmation dialog with filename
    ├─ If confirmed: Add to pathsToDelete[]
    └─ If cancelled: Skip this file
    ↓
Frontend: POST /api/delete with pathsToDelete
    ↓
Backend: Delete files
    ↓
Backend: Return removed list
    ↓
Frontend: Display results
    ↓
Frontend: Auto-scan to refresh
```

---

## Configuration

### Environment Variables
- `MUSIC_INBOX`: Folder to scan (default: `/inbox`)
- `RENAME_TEMPLATE`: Filename pattern (default: `"{artist} - {title}"`)

### Supported Audio Formats
`.mp3`, `.flac`, `.m4a`, `.ogg`, `.wav`, `.opus`, `.aac`

### Filename Sanitization
Only these characters are replaced with `_`:
```
\ / : * ? " < > |
```
All other characters (parentheses, quotes, dashes, etc.) are preserved.

---

## Common Development Tasks

### Adding a New Feature to the UI

1. **Add UI element** in `index.html` (HTML section)
2. **Add styling** in `<style>` section
3. **Add JavaScript function** in `<script>` section
4. **Wire up event handler** (onclick, oninput, etc.)
5. **Update state** (`CURRENT_ITEMS` or new state variable)
6. **Re-render** if needed (`renderItems()`)

### Adding a New API Endpoint

1. **Define route** in `app/app.py`:
   ```python
   @app.route('/api/newfeature', methods=['POST'])
   def new_feature():
       data = request.get_json()
       # Process data
       return jsonify({"ok": True, "result": result})
   ```

2. **Add frontend function** in `index.html`:
   ```javascript
   async function callNewFeature() {
       const j = await call('/api/newfeature', { data: 'value' });
       setOut(j);
   }
   ```

3. **Add button** to toolbar:
   ```html
   <button class="btn" onclick="callNewFeature()">New Feature</button>
   ```

### Modifying Filename Parsing Logic

Edit `parse_artist_title_from_filename()` in `app/app.py`:
- This function uses regex patterns to extract artist/title
- Priority: filename parsing > embedded tags (fallback only)
- Test with various filename formats

### Changing Rename Template

1. **Server-side**: Set `RENAME_TEMPLATE` environment variable
2. **Client-side**: Template is fetched via `/api/settings`
3. **Preview**: `buildPreviewName()` uses template for live preview

---

## UI Components Reference

### Buttons
```html
<button class="btn">Normal</button>
<button class="btn primary">Primary (blue)</button>
<button class="btn danger">Danger (red)</button>
```

### CSS Variables (Theme)
```css
--bg: Background color
--fg: Foreground (text) color
--muted: Muted text color
--panel: Panel/input background
--border: Border color
--accent: Primary accent (blue)
--danger: Danger color (red)
--mono-bg: Monospace background (output)
--mono-fg: Monospace foreground (output)
```

### Table Structure
```html
<table id="tbl">
  <thead>
    <tr>
      <th class="w-checkbox">Checkbox</th>
      <th class="w-path">File path</th>
      <th class="w-artist">Artist (editable)</th>
      <th class="w-title">Title (editable)</th>
      <th>Extension</th>
      <th class="w-date sortable">Date/Time</th>
      <th class="w-prev">Preview name</th>
    </tr>
  </thead>
  <tbody><!-- Rendered by renderItems() --></tbody>
</table>
```

---

## Testing Checklist

When making changes, verify:

- [ ] **Scan**: Files are listed correctly
- [ ] **Filter**: Search works for filename, artist, title
- [ ] **Edit**: Artist/Title edits update preview live
- [ ] **Sort**: Date/Time sorting works (toggle ▼/▲)
- [ ] **Select**: Select all/none works with filtered items
- [ ] **Preview**: Shows correct target names and collisions
- [ ] **Rename**: Files are renamed correctly in-place
- [ ] **Delete**: Selected files are deleted with confirmations
- [ ] **Conflicts**: Name collisions are resolved with (1), (2), etc.
- [ ] **Errors**: Error messages are clear and actionable
- [ ] **Dark mode**: UI looks good in both light and dark themes

---

## Debugging Tips

### Backend Issues
```bash
# View container logs
docker logs --tail=200 music-renamer

# Check file permissions
ls -la /path/to/inbox

# Test API directly
curl -X POST http://localhost:8080/api/scan \
  -H "Content-Type: application/json" \
  -d '{}'
```

### Frontend Issues
- Open browser DevTools (F12)
- Check Console for JavaScript errors
- Check Network tab for API responses
- Inspect `CURRENT_ITEMS` and `FILTERED_ITEMS` in console

### Common Issues
1. **"Invalid JSON response"**: Check backend logs for Python exceptions
2. **Files not renaming**: Check permissions, verify file exists
3. **Preview doesn't match result**: Check `RENAME_TEMPLATE` consistency
4. **Search not working**: Verify `SEARCH_TERM` is set correctly

---

## Code Style Guidelines

### Python (Backend)
- Use 4 spaces for indentation
- Follow PEP 8 conventions
- Use type hints where helpful
- Keep functions focused and small
- Always return JSON from API endpoints

### JavaScript (Frontend)
- Use 2 spaces for indentation
- Use `const` and `let`, avoid `var`
- Use async/await for API calls
- Keep functions pure when possible
- Use descriptive variable names

### HTML/CSS
- Use semantic HTML5 elements
- Use CSS custom properties for theming
- Keep styles in `<style>` section
- Use BEM-like naming for classes

---

## Security Considerations

⚠️ **This application is designed for LAN-only use**

- No authentication/authorization
- No input validation beyond filename sanitization
- Delete endpoint accepts absolute paths
- Expose only on trusted networks
- Consider reverse proxy with Basic Auth for additional security

---

## Performance Notes

- **No pagination**: All files loaded at once (suitable for <10,000 files)
- **Client-side filtering**: Fast for typical music collections
- **Atomic renames**: `os.replace()` is atomic within same filesystem
- **No database**: Stateless, no persistence overhead

---

## Future Enhancement Ideas

- [ ] Batch edit (apply same artist to multiple files)
- [ ] Undo last rename operation
- [ ] Export/import rename plans
- [ ] Regex-based bulk find/replace
- [ ] Custom filename templates per session
- [ ] Drag-and-drop file upload
- [ ] Audio preview player
- [ ] Tag writing (currently read-only)
- [ ] Multi-folder support
- [ ] Pagination for large collections

---

## Quick Reference: File Locations

| What | Where |
|------|-------|
| API endpoints | `app/app.py` |
| UI layout | `app/templates/index.html` (HTML section) |
| Styles | `app/templates/index.html` (`<style>` section) |
| JavaScript | `app/templates/index.html` (`<script>` section) |
| Dependencies | `requirements.txt` |
| Docker config | `docker/Dockerfile`, `compose.yaml` |
| Documentation | `README (1).md`, `CONTEXT.md` |

---

## Contact & Support

For issues or questions:
1. Check logs: `docker logs music-renamer`
2. Review this context document
3. Check `README (1).md` for user documentation
4. Verify environment variables and volume mounts

---

**Last Updated**: 2026-04-10  
**Version**: 1.1 (with delete selected feature)