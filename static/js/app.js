let state = {
  allRows: [],
  matchedRow: null,
  row_index: null,
  studentName: "",
  examRollNo: "",
  school: "",
  standard: "",
  division: "",
  rollNumber: "",
  set: "",
  mcqTotal: "",
  essayMarks: "",
  totalScore: "",
  ap:0, aq:0, ar:0, as:0, at:0, au:0, av:0, aw:0, ax:0
};

async function init() {
  const res = await fetch("/api/students");
  const data = await res.json();
  state.allRows = data.rows;
  populateDropdowns();
}

function populateDropdowns() {
  const dummySchools = [
    "Cygnus World School",
    "Vatsalya International School",
    "Delhi Public School",
    "Swayam Cambridge International School",
    "Gangotri International School"
  ];
  let schools = [...new Set(state.allRows.map(r => r[3]))].filter(s => s && String(s).trim());
  schools = [...new Set([...schools, ...dummySchools])].sort();
  const schoolSelect = document.getElementById('school-select');
  schools.forEach(s => {
    const opt = document.createElement('option');
    opt.value = opt.textContent = s;
    schoolSelect.appendChild(opt);
  });

  const stdSelect = document.getElementById('std-select');
  [...new Set(state.allRows.map(r => r[4]))].sort().forEach(s => {
    const opt = document.createElement('option');
    opt.value = opt.textContent = s;
    stdSelect.appendChild(opt);
  });

  const divSelect = document.getElementById('div-select');
  [...new Set(state.allRows.map(r => r[5]))].sort().forEach(s => {
    const opt = document.createElement('option');
    opt.value = opt.textContent = s;
    divSelect.appendChild(opt);
  });
}

document.getElementById('identify-form').onsubmit = (e) => {
  e.preventDefault();
  const school = document.getElementById('school-select').value;
  const std = document.getElementById('std-select').value;
  const div = document.getElementById('div-select').value;
  const roll = document.getElementById('roll-input').value;

  const match = state.allRows.find((r, idx) => {
    if (r[3] === school && String(r[4]) === std && r[5] === div && String(r[6]) === roll) {
      state.row_index = idx;
      return true;
    }
    return false;
  });

  if (match) {
    state.matchedRow = match;
    state.studentName = match[2];
    state.examRollNo = match[1];
    state.school = match[3];
    state.standard = match[4];
    state.division = match[5];
    state.rollNumber = match[6];
    state.set = match[7];
    state.mcqTotal = match[48];
    state.essayMarks = match[49];
    state.totalScore = match[50];
    
    // Topic scores
    const labels = ['ap','aq','ar','as','at','au','av','aw','ax'];
    labels.forEach((l, i) => state[l] = match[39 + i]);

    document.getElementById('found-name').textContent = state.studentName;
    document.getElementById('student-found-card').classList.remove('hidden');
    document.getElementById('p1-error').classList.add('hidden');
  } else {
    document.getElementById('p1-error').textContent = "Student not found. Check details.";
    document.getElementById('p1-error').classList.remove('hidden');
  }
};

function goToPage2() {
  document.getElementById('page-1').classList.remove('active');
  document.getElementById('page-2').classList.add('active');
  document.getElementById('p2-student-name-banner').textContent = `Identifying: ${state.studentName}`;
}

async function sendOtp() {
  const phone = document.getElementById('phone-input').value;
  if (phone.length !== 10) return alert("Enter 10-digit mobile");

  const res = await fetch("/api/send-otp", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ phone_number: phone })
  });
  
  if (res.ok) {
    document.getElementById('otp-section').classList.remove('hidden');
    document.getElementById('sms-sent-number').textContent = phone;
  } else {
    alert("Failed to send OTP");
  }
}

async function verifyOtp() {
  const phone = document.getElementById('phone-input').value;
  const otp = document.getElementById('otp-input').value;
  
  const res = await fetch("/api/verify-otp", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ phone_number: phone, otp: otp, row_index: state.row_index })
  });

  if (res.ok) {
    showResultPage();
  } else {
    document.getElementById('otp-error').textContent = "Invalid OTP";
    document.getElementById('otp-error').classList.remove('hidden');
  }
}

function showResultPage() {
  document.getElementById('page-2').classList.remove('active');
  document.getElementById('page-3').classList.add('active');

  document.getElementById('res-student-name').textContent = state.studentName;
  document.getElementById('res-exam-roll').textContent = state.examRollNo;
  document.getElementById('res-school').textContent = state.school;
  document.getElementById('res-std').textContent = state.standard;
  document.getElementById('res-div').textContent = state.division;
  document.getElementById('res-total').textContent = state.totalScore;

  const initials = state.studentName.split(" ").map(n => n[0]).join("").toUpperCase();
  document.getElementById('result-avatar-initials').textContent = initials;

  const topics = ['ap','aq','ar','as','at','au','av','aw','ax'];
  topics.forEach(t => {
    const el = document.getElementById(`res-${t}`);
    const val = parseFloat(state[t]);
    el.textContent = state[t];
    
    const row = el.closest('.cs-row');
    row.classList.remove('cs-maroon','cs-darkorange','cs-lightyellow','cs-darkgreen','cs-brightgreen');
    if (val <= 20) row.classList.add('cs-maroon');
    else if (val <= 40) row.classList.add('cs-darkorange');
    else if (val <= 60) row.classList.add('cs-lightyellow');
    else if (val <= 80) row.classList.add('cs-darkgreen');
    else row.classList.add('cs-brightgreen');
  });
}

function downloadResultPDF() { window.print(); }
function checkAnotherResult() { location.reload(); }

init();
