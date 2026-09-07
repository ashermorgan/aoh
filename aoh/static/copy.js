// Feather icons
const COPY_SVG = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>';
const DONE_SVG = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>'

// Show copy button only if browser supports JavaScript and clipboard API
function show_copy_btn() {
    if ('clipboard' in navigator) {
        document.getElementById('copy').innerHTML = COPY_SVG;
        document.getElementById('copy').hidden = false;
    }
}

// Copy command to clipboard
function copy(cmd) {
    navigator.clipboard.writeText(cmd);

    document.getElementById('copy').disabled = true;
    document.getElementById('copy').innerHTML = DONE_SVG;
    setTimeout(() => {
        document.getElementById('copy').innerHTML = COPY_SVG;
        document.getElementById('copy').disabled = false;
    }, 1000);
}
