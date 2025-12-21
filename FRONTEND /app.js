const API = "http://127.0.0.1:8000";
const STAGIAIRE_ID = localStorage.getItem("stagiaireId");
const TOKEN = localStorage.getItem("token");

// ---------- LOGIN ----------
async function login() {
    const res = await fetch(`${API}/api/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            email: email.value,
            password: password.value
        })
    });

    const data = await res.json();
    localStorage.setItem("token", data.access_token);
    loginStatus.innerText = "Connecté";
}

// ---------- UPLOAD CV ----------
async function uploadCV() {
    const file = document.getElementById("cvFile").files[0];
    const form = new FormData();
    form.append("file", file);

    const res = await fetch(`${API}/api/stagiaires/${STAGIAIRE_ID}/upload-cv`, {
        method: "POST",
        headers: { "Authorization": "Bearer " + TOKEN },
        body: form
    });

    cvStatus.innerText = "CV envoyé ✔";
}

// ---------- OFFRES ----------
async function loadOffres() {
    const res = await fetch(`${API}/api/offres`);
    const data = await res.json();
    offres.innerHTML = data.map(o =>
        `<p>${o.titre} - ${o.ville}
     <button onclick="postuler('${o.id}')">Candidater</button></p>`
    ).join("");
}

// ---------- CANDIDATER ----------
async function postuler(offreId) {
    await fetch(`${API}/api/candidater`, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            "Authorization": "Bearer " + TOKEN
        },
        body: JSON.stringify({
            stagiaireId: STAGIAIRE_ID,
            offreId: offreId
        })
    });
    alert("Candidature envoyée");
}

// ---------- RECO IA ----------
async function loadReco() {
    const res = await fetch(`${API}/api/recommandations/${STAGIAIRE_ID}`);
    const data = await res.json();
    reco.innerHTML = data.map(r =>
        `<li>${r.titre} (score ${r.score})</li>`
    ).join("");
}

loadOffres();
loadReco();
document.getElementById('searchForm').addEventListener('submit', function (e) {
    e.preventDefault(); // prevent default form submission
    const query = document.getElementById('searchInput').value.trim();
    if (query) {
        // Redirect to results page with query as a parameter
        window.location.href = `search_results.html?q=${encodeURIComponent(query)}`;
    }
});
