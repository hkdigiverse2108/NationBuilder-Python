let allRows = [];

async function init() {
    const res = await fetch("/api/students");
    const data = await res.json();
    allRows = data.rows;
    populateDropdowns();
}

function populateDropdowns() {
    const schoolSelect = document.getElementById('school-select');
    const stdSelect = document.getElementById('std-select');
    const divSelect = document.getElementById('div-select');

    let schools = [...new Set(allRows.map(r => r[3]))]
        .map(s => String(s).trim())
        .filter(s => s && s !== "nan");
    schools = [...new Set(schools)].sort();
    
    schools.forEach(s => {
        const opt = document.createElement('option');
        opt.value = opt.textContent = s;
        schoolSelect.appendChild(opt);
    });

    const stds = [...new Set(allRows.map(r => r[4]))].filter(s => s && String(s).trim()).sort();
    stds.forEach(s => {
        const opt = document.createElement('option');
        opt.value = opt.textContent = s;
        stdSelect.appendChild(opt);
    });

    const divs = [...new Set(allRows.map(r => r[5]))].filter(d => d && String(d).trim()).sort();
    divs.forEach(d => {
        const opt = document.createElement('option');
        opt.value = opt.textContent = d;
        divSelect.appendChild(opt);
    });
}

document.getElementById('identify-form').onsubmit = (e) => {
    e.preventDefault();
    const school = document.getElementById('school-select').value;
    const std = document.getElementById('std-select').value;
    const div = document.getElementById('div-select').value;
    const roll = document.getElementById('roll-input').value;
    const phone = document.getElementById('phone-input').value;

    // Phone validation: 10 digits, starts with 6,7,8,9
    const phoneRegex = /^[6-9]\d{9}$/;
    if (!phoneRegex.test(phone)) {
        const errorEl = document.getElementById('p1-error');
        errorEl.textContent = "Invalid mobile number. It must be 10 digits and start with 6, 7, 8, or 9.";
        errorEl.classList.remove('hidden');
        return;
    }

    const idx = allRows.findIndex(r => 
        r[3] === school && String(r[4]) === std && r[5] === div && String(r[6]) === roll
    );

    if (idx !== -1) {
        document.getElementById('found-name').textContent = allRows[idx][2];
        document.getElementById('student-found-card').classList.remove('hidden');
        document.getElementById('p1-error').classList.add('hidden');
        
        document.getElementById('view-result-btn').onclick = async () => {
            // Save number to backend
            await fetch("/api/save-number", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    name: allRows[idx][2],
                    phone: phone,
                    roll_no: allRows[idx][1],
                    school: allRows[idx][3]
                })
            });

            const selectRes = await fetch("/api/select-student", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ row_index: idx })
            });
            if (selectRes.ok) window.location.href = "/result";
        };
    } else {
        document.getElementById('p1-error').textContent = "Student not found. Please verify details.";
        document.getElementById('p1-error').classList.remove('hidden');
        document.getElementById('student-found-card').classList.add('hidden');
    }
};

init();
