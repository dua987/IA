async function loadStats() {
    const res = await fetch(`http://127.0.0.1:8000/api/stats/stagiaire/${STAGIAIRE_ID}`);
    const data = await res.json();

    new Chart(document.getElementById("statsChart"), {
        type: "bar",
        data: {
            labels: Object.keys(data.par_ville),
            datasets: [{
                label: "Candidatures",
                data: Object.values(data.par_ville)
            }]
        }
    });
}

loadStats();
