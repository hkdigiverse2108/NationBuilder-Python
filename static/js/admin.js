document.addEventListener('DOMContentLoaded', async () => {
    const tableBody = document.getElementById('admin-table-body');
    const searchInput = document.getElementById('admin-search');
    let allStudents = [];

    // 1. Fetch data from existing student API
    // We can reuse /api/students as it returns everything
    try {
        const response = await fetch('/api/students');
        const data = await response.json();
        
        if (data && data.rows) {
            allStudents = data.rows;
            renderTable(allStudents);
        } else {
            tableBody.innerHTML = '<tr><td colspan="6" class="no-data">No student data found in the CSV.</td></tr>';
        }
    } catch (err) {
        console.error("Failed to fetch students for admin:", err);
        tableBody.innerHTML = '<tr><td colspan="6" class="no-data" style="color:red;">Error loading student database.</td></tr>';
    }

    // 2. Render function
    function renderTable(students) {
        if (students.length === 0) {
            tableBody.innerHTML = '<tr><td colspan="6" class="no-data">No students match your search.</td></tr>';
            return;
        }

        tableBody.innerHTML = students.map(student => `
            <tr>
                <td style="font-weight:700; color:var(--navy);">${student[1]}</td>
                <td style="font-family:'Playfair Display', serif; font-size:1rem; font-weight:700;">${student[2]}</td>
                <td style="font-size:0.85rem; color:var(--text-soft); font-weight:600;">${student[3]}</td>
                <td><span class="badge-roll" style="background:#f1f5f9; color:var(--navy); border:1px solid #e2e8f0; border-radius:4px;">Std. ${student[4]}</span></td>
                <td>${student[5]}</td>
                <td style="font-weight:800; color:#059669;">${student[40]}</td>
            </tr>
        `).join('');
    }

    // 3. Search Logic
    searchInput.addEventListener('input', (e) => {
        const term = e.target.value.toLowerCase();
        const filtered = allStudents.filter(s => 
            String(s[1]).toLowerCase().includes(term) || // Exam Roll
            String(s[2]).toLowerCase().includes(term) || // Name
            String(s[3]).toLowerCase().includes(term) || // School
            String(s[4]).toLowerCase().includes(term)    // Std
        );
        renderTable(filtered);
    });

    // 4. Fetch and render leads (collected numbers)
    const leadsTableBody = document.getElementById('leads-table-body');
    try {
        const leadsResponse = await fetch('/admin/collected-numbers');
        const leadsData = await leadsResponse.json();
        
        if (leadsData && leadsData.rows && leadsData.rows.length > 0) {
            leadsTableBody.innerHTML = leadsData.rows.reverse().map(row => `
                <tr>
                    <td style="font-size:0.8rem; color:var(--text-soft);">${row[0]}</td>
                    <td style="font-weight:700;">${row[1]}</td>
                    <td style="font-weight:800; color:var(--navy);">${row[2]}</td>
                    <td>${row[3]}</td>
                    <td style="font-size:0.85rem;">${row[4]}</td>
                </tr>
            `).join('');
        } else {
            leadsTableBody.innerHTML = '<tr><td colspan="5" class="no-data">No numbers collected yet.</td></tr>';
        }
    } catch (err) {
        console.error("Failed to fetch leads for admin:", err);
        leadsTableBody.innerHTML = '<tr><td colspan="5" class="no-data" style="color:red;">Error loading leads database.</td></tr>';
    }
});
