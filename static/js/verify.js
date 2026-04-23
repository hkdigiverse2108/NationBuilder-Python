let currentPhone = "";

async function init() {
    const res = await fetch("/api/current-student");
    if (!res.ok) {
        window.location.href = "/";
        return;
    }
    const data = await res.json();
    document.getElementById('p2-student-name-banner').textContent = `Identifying: ${data.student[2]}`;
}

document.getElementById('send-otp-btn').onclick = async () => {
    const phone = document.getElementById('phone-input').value;
    if (phone.length !== 10) return alert("Please enter a valid 10-digit mobile number.");
    
    currentPhone = phone;
    const res = await fetch("/api/send-otp", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ phone_number: phone })
    });
    
    if (res.ok) {
        const data = await res.json();
        if (data.already_verified) {
            // Returning user — phone already verified for this student, go straight to result
            window.location.href = "/result";
        } else {
            // New access — show OTP input
            document.getElementById('otp-section').classList.remove('hidden');
            document.getElementById('sms-sent-number').textContent = phone;
            document.getElementById('send-otp-btn').textContent = "Resend OTP";
        }
    } else {
        const errorData = await res.json().catch(() => ({}));
        const msg = errorData.detail || "Failed to send OTP. Please try again.";
        document.getElementById('otp-error').textContent = msg;
        document.getElementById('otp-error').classList.remove('hidden');
    }
};

document.getElementById('verify-otp-btn').onclick = async () => {
    const otp = document.getElementById('otp-input').value;
    const res = await fetch("/api/current-student");
    const sessionData = await res.json();

    const verifyRes = await fetch("/api/verify-otp", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ 
            phone_number: currentPhone, 
            otp: otp, 
            row_index: sessionData.row_index 
        })
    });

    if (verifyRes.ok) {
        window.location.href = "/result";
    } else {
        const errorData = await verifyRes.json();
        document.getElementById('otp-error').textContent = errorData.detail || "Invalid OTP";
        document.getElementById('otp-error').classList.remove('hidden');
    }
};

init();
