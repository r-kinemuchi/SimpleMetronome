'use strict';

const state = {
  bpm: 120,
  beats: 4,
  isPlaying: false,
};

// ---- Beat callback (called by Python via evaluate_js) ----
window.onBeat = function(beatIndex, isAccent, isSub) {
  if (beatIndex < 0) {
    renderBeatIndicators(-1);
    return;
  }
  if (!isSub) {
    renderBeatIndicators(beatIndex, isAccent);
  }
};

// ---- Beat indicators ----
function buildBeatDots(count) {
  const container = document.getElementById('beat-indicators');
  container.innerHTML = '';
  for (let i = 0; i < count; i++) {
    const dot = document.createElement('div');
    dot.className = 'beat-dot' + (i === 0 ? ' first' : '');
    container.appendChild(dot);
  }
  state.beats = count;
}

function renderBeatIndicators(activeBeat, isAccent) {
  const dots = document.querySelectorAll('.beat-dot');
  dots.forEach((dot, i) => {
    const active = i === activeBeat;
    dot.classList.toggle('active', active);
    if (active && isAccent && i === 0) {
      dot.classList.add('first');
    }
  });
}

// ---- State helpers ----
function updateBPM(bpm) {
  state.bpm = bpm;
  const rounded = Math.round(bpm);
  document.getElementById('bpm-display').textContent = rounded;
  document.getElementById('bpm-slider').value = rounded;
  document.getElementById('bpm-input').value = rounded;
}

function setPlayState(isPlaying) {
  state.isPlaying = isPlaying;
  const btn = document.getElementById('btn-play');
  btn.textContent = isPlaying ? '■ STOP' : '▶ START';
  btn.classList.toggle('playing', isPlaying);
  if (!isPlaying) renderBeatIndicators(-1);
}

function applyState(s) {
  updateBPM(s.bpm);
  setPlayState(s.is_playing);
  buildBeatDots(s.beats);
  document.getElementById('time-sig-select').value = s.time_signature;
  document.getElementById('subdivision-select').value = String(s.subdivision);
  document.getElementById('sound-select').value = s.sound;
  document.getElementById('volume-slider').value = Math.round(s.volume * 100);
}

// ---- Init ----
window.addEventListener('pywebviewready', async () => {
  const api = window.pywebview.api;

  const s = await api.get_state();
  applyState(s);

  document.getElementById('btn-play').addEventListener('click', async () => {
    const result = await api.toggle_play();
    setPlayState(result.is_playing);
  });

  document.getElementById('btn-tap').addEventListener('click', async () => {
    const result = await api.tap_tempo();
    updateBPM(result.bpm);
  });

  document.getElementById('bpm-slider').addEventListener('input', async (e) => {
    const result = await api.set_bpm(Number(e.target.value));
    updateBPM(result.bpm);
  });

  document.getElementById('bpm-input').addEventListener('change', async (e) => {
    const result = await api.set_bpm(Number(e.target.value));
    updateBPM(result.bpm);
  });

  document.getElementById('btn-inc').addEventListener('click', async () => {
    const result = await api.set_bpm(state.bpm + 1);
    updateBPM(result.bpm);
  });

  document.getElementById('btn-dec').addEventListener('click', async () => {
    const result = await api.set_bpm(state.bpm - 1);
    updateBPM(result.bpm);
  });

  document.getElementById('volume-slider').addEventListener('input', async (e) => {
    await api.set_volume(Number(e.target.value) / 100);
  });

  document.getElementById('time-sig-select').addEventListener('change', async (e) => {
    const result = await api.set_time_signature(e.target.value);
    buildBeatDots(result.beats);
    renderBeatIndicators(-1);
  });

  document.getElementById('subdivision-select').addEventListener('change', async (e) => {
    await api.set_subdivision(Number(e.target.value));
  });

  document.getElementById('sound-select').addEventListener('change', async (e) => {
    await api.set_sound(e.target.value);
  });

  document.addEventListener('keydown', (e) => {
    if (e.target.tagName === 'INPUT') return;
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      document.getElementById('btn-play').click();
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      document.getElementById('btn-inc').click();
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      document.getElementById('btn-dec').click();
    } else if (e.key === 't' || e.key === 'T') {
      document.getElementById('btn-tap').click();
    }
  });
});
