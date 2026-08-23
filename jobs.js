(function () {
  const C = {
    green: '#6B9E78',
    gd: '#3d6b47',
    blue: '#4A90C4',
    orange: '#E07A40',
    purple: '#9B59B6',
    grid: '#E8EBE8'
  };

  const nf0 = new Intl.NumberFormat('da-DK', { maximumFractionDigits: 0 });
  const nf1 = new Intl.NumberFormat('da-DK', { minimumFractionDigits: 1, maximumFractionDigits: 1 });

  function mp(v) {
    const m = String(v || '').match(/^(\d{4})M(\d{2})$/);
    if (m) {
      return ['jan.', 'feb.', 'mar.', 'apr.', 'maj', 'jun.', 'jul.', 'aug.', 'sep.', 'okt.', 'nov.', 'dec.'][+m[2] - 1] + ' ' + m[1];
    }
    return String(v || '');
  }

  function sp(v) {
    const m = String(v || '').match(/^(\d{4})M(\d{2})$/);
    return m ? m[2] + '/' + m[1].slice(2) : v;
  }

  function kpi(label, value, detail) {
    return `<div class="kpi"><small>${label}</small><strong>${value}</strong><span>${detail || ''}</span></div>`;
  }

  function baseOpts(zero = true) {
    return {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: {
          position: 'top',
          align: 'start',
          labels: { usePointStyle: true, padding: 18 }
        },
        tooltip: { backgroundColor: '#0F2B36', padding: 11 }
      },
      scales: {
        x: {
          type: 'category',
          grid: { display: false },
          ticks: {
            maxRotation: 0,
            autoSkip: true,
            callback: function (v, i) {
              const labels = this.chart.data.labels || [];
              return sp(labels[v] ?? labels[i] ?? v);
            }
          }
        },
        y: {
          beginAtZero: zero,
          grid: { color: C.grid }
        }
      }
    };
  }

  function line(id, labels, sets, zero = true) {
    new Chart(document.getElementById(id), {
      type: 'line',
      data: { labels, datasets: sets },
      options: baseOpts(zero)
    });
  }

  function recruitment(id, labels, attempts, rate) {
    const options = baseOpts(true);
    options.scales.y1 = {
      beginAtZero: true,
      position: 'right',
      grid: { drawOnChartArea: false },
      ticks: { callback: v => nf1.format(v) + ' %' }
    };

    new Chart(document.getElementById(id), {
      type: 'bar',
      data: {
        labels,
        datasets: [
          {
            label: 'Forgæves rekrutteringsforsøg',
            data: attempts,
            backgroundColor: C.green,
            yAxisID: 'y'
          },
          {
            type: 'line',
            label: 'Forgæves rekrutteringsrate',
            data: rate,
            borderColor: C.orange,
            backgroundColor: C.orange,
            pointRadius: 0,
            borderWidth: 2.4,
            yAxisID: 'y1'
          }
        ]
      },
      options
    });
  }

  function wrapLabel(text, maxChars = 27) {
    const words = String(text || '').split(/\s+/);
    const lines = [];
    let line = '';
    for (const word of words) {
      const next = line ? line + ' ' + word : word;
      if (line && next.length > maxChars) {
        lines.push(line);
        line = word;
      } else {
        line = next;
      }
    }
    if (line) lines.push(line);
    return lines;
  }

  function niceStep(maxValue) {
    if (!Number.isFinite(maxValue) || maxValue <= 0) return 1;
    const rough = maxValue / 5;
    const power = Math.pow(10, Math.floor(Math.log10(rough)));
    const normalized = rough / power;
    const nice = normalized <= 1 ? 1 : normalized <= 2 ? 2 : normalized <= 5 ? 5 : 10;
    return nice * power;
  }

  function hbar(id, items) {
    const values = items.map(x => Number(x.value) || 0);
    const maxValue = Math.max(0, ...values);
    const step = niceStep(maxValue);
    const axisMax = Math.max(step, Math.ceil(maxValue / step) * step);

    new Chart(document.getElementById(id), {
      type: 'bar',
      data: {
        labels: items.map(x => x.name),
        datasets: [{
          label: 'Forgæves rekrutteringsforsøg',
          data: values,
          backgroundColor: C.blue,
          borderWidth: 0,
          borderRadius: 3
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        indexAxis: 'y',
        interaction: { mode: 'nearest', axis: 'y', intersect: false },
        layout: { padding: { left: 4, right: 18 } },
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: '#0F2B36',
            padding: 11,
            callbacks: {
              title: ctx => ctx.length ? items[ctx[0].dataIndex]?.name || '' : '',
              label: ctx => nf0.format(ctx.raw) + ' forgæves rekrutteringsforsøg'
            }
          }
        },
        scales: {
          x: {
            type: 'linear',
            beginAtZero: true,
            max: axisMax,
            grid: { color: C.grid },
            border: { display: false },
            title: {
              display: true,
              text: 'Antal forgæves rekrutteringsforsøg',
              color: '#4A5A5F',
              font: { size: 12, weight: '600' }
            },
            ticks: {
              stepSize: step,
              precision: 0,
              color: '#4A5A5F',
              callback: value => nf0.format(value)
            }
          },
          y: {
            type: 'category',
            grid: { display: false },
            border: { display: false },
            ticks: {
              autoSkip: false,
              color: '#4A5A5F',
              padding: 8,
              font: { size: 12 },
              callback: function (value) {
                return wrapLabel(this.getLabelForValue(value));
              }
            }
          }
        }
      }
    });
  }

  (async function () {
    try {
      const response = await fetch(
        'https://ai-michelklos.github.io/Dashboard/data/dashboard-data.json?v=' + Date.now(),
        { cache: 'no-store' }
      );
      if (!response.ok) throw new Error(response.status);

      const data = await response.json();
      const vacanciesData = data.vacancies || {};
      const failed = data.failedRecruitment || {};
      const unemployment = data.unemployment || {};

      document.getElementById('updated').textContent = data.meta?.updateStatus?.checkedAt
        ? 'Data kontrolleret ' + new Date(data.meta.updateStatus.checkedAt).toLocaleDateString('da-DK', { dateStyle: 'long' })
        : '';

      const vi = (vacanciesData.labels || []).length - 1;
      const fi = (failed.labels || []).length - 1;
      const ui = (unemployment.labels || []).length - 1;
      const vacancies = vi >= 0 ? vacanciesData.values?.[vi] : null;
      const attempts = fi >= 0 ? failed.attempts?.[fi] : null;
      const rate = fi >= 0 ? failed.rate?.[fi] : null;
      const unemp = ui >= 0 ? unemployment.total?.[ui] : null;

      document.getElementById('kpis').innerHTML =
        kpi('Nyopslåede stillinger', vacancies == null ? 'Ikke tilgængelig' : nf0.format(vacancies), vi >= 0 ? mp(vacanciesData.labels[vi]) : '') +
        kpi('Forgæves rekrutteringsforsøg', attempts == null ? 'Ikke tilgængelig' : nf0.format(attempts), fi >= 0 ? mp(failed.labels[fi]) : '') +
        kpi('Forgæves rekrutteringsrate', rate == null ? 'Ikke tilgængelig' : nf1.format(rate) + ' %', fi >= 0 ? mp(failed.labels[fi]) : '') +
        kpi('Bruttoledige', unemp == null ? 'Ikke tilgængelig' : nf0.format(unemp), ui >= 0 ? mp(unemployment.labels[ui]) : '');

      line('vacancies', vacanciesData.labels || [], [{
        label: 'Nyopslåede stillinger',
        data: vacanciesData.values || [],
        borderColor: C.blue,
        backgroundColor: C.blue,
        pointRadius: 0
      }], true);

      recruitment('recruitment', failed.labels || [], failed.attempts || [], failed.rate || []);
      hbar('occupations', failed.topOccupations || []);

      const sourceStatus = data.meta?.sourceStatus?.failedRecruitment;
      if (sourceStatus?.latestPeriod) {
        document.getElementById('surveyPeriod').textContent = mp(sourceStatus.latestPeriod);
      }
      document.getElementById('topPeriod').textContent = mp(failed.topPeriod || sourceStatus?.latestPeriod);

      if (data.meta?.updateStatus?.state !== 'ok') {
        const el = document.getElementById('status');
        el.style.display = 'block';
        el.textContent = 'Hoveddashboardets seneste dataopdatering er ikke fuldt gennemført.';
      }
    } catch (error) {
      const el = document.getElementById('status');
      el.style.display = 'block';
      el.textContent = 'Data kunne ikke indlæses fra hoveddashboardet.';
      console.error(error);
    }
  })();
})();
