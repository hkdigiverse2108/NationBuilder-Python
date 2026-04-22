async function init() {
    const res = await fetch("/api/current-student");
    if (!res.ok) {
        window.location.href = "/";
        return;
    }
    const data = await res.json();
    renderResult(data.student);
}

function renderResult(row) {
    document.getElementById('res-student-name').textContent = row[2];
    document.getElementById('res-exam-roll').textContent = row[1];
    document.getElementById('res-school-roll').textContent = row[6] || "—";
    document.getElementById('res-school').textContent = row[3];
    document.getElementById('res-std').textContent = row[4];
    document.getElementById('res-div').textContent = row[5];
    document.getElementById('res-total').textContent = row[40];

    const topics = ['ap','aq','ar','as','at','au','av','aw','ax'];
    topics.forEach((t, i) => {
        const rawVal = row[41 + i];
        const val = (rawVal !== undefined && rawVal !== "") ? parseFloat(rawVal) : NaN;
        const el = document.getElementById(`res-${t}`);
        if (!el) return;
        
        // Ensure marks are visible and rounded
        el.textContent = isNaN(val) ? "—" : (Number.isInteger(val) ? val + "%" : val.toFixed(1) + "%");
        
        const card = el.closest('.cs-row');
        if (!card) return;
        
        card.classList.remove('cs-maroon','cs-darkorange','cs-lightyellow','cs-darkgreen','cs-brightgreen');
        
        if (!isNaN(val)) {
            if (val <= 20) card.classList.add('cs-maroon');
            else if (val <= 40) card.classList.add('cs-darkorange');
            else if (val <= 60) card.classList.add('cs-lightyellow');
            else if (val <= 80) card.classList.add('cs-darkgreen');
            else card.classList.add('cs-brightgreen');
        }
    });
}

async function downloadPdf() {
    const btn = document.querySelector('.btn-download');
    const originalText = btn.innerHTML;
    
    try {
        btn.innerHTML = '<span>⌛ Generating...</span>';
        btn.disabled = true;

        const response = await fetch('/api/download-result-pdf');
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.detail || 'Internal server error');
        }

        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        const rawRoll = document.getElementById('res-exam-roll').textContent || 'Student';
        const roll = rawRoll.replace(/[^a-zA-Z0-9_\-]/g, '_');
        a.download = `Result_Roll_${roll}.pdf`;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        a.remove();
    } catch (err) {
        console.error('PDF Error:', err);
        // Try to get the error detail from the response if possible
        let msg = 'Failed to generate PDF. Please try again or use Ctrl+P to print.';
        if (err.message) msg += `\n\nError: ${err.message}`;
        alert(msg);
    } finally {
        btn.innerHTML = originalText;
        btn.disabled = false;
    }
}

init();