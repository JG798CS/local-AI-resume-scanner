const appRoot = document.getElementById('app');
const pageTitle = document.getElementById('page-title');
const statusBanner = document.getElementById('status-banner');
const stages = ['initial_screen', 'first_round', 'second_round'];

function setTitle(title) { pageTitle.textContent = title; }
function setStatus(message, kind = 'success') {
  if (!message) {
    statusBanner.textContent = '';
    statusBanner.className = 'status-banner hidden';
    return;
  }
  statusBanner.textContent = message;
  statusBanner.className = `status-banner ${kind}`;
}
function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}
function badge(label, type = '') { return `<span class="badge ${type}">${escapeHtml(label)}</span>`; }
function sectionList(items, emptyText = 'None') {
  if (!items || items.length === 0) return `<div class="list-item">${escapeHtml(emptyText)}</div>`;
  return items.map((item) => `<div class="list-item">${item}</div>`).join('');
}
async function api(path, options = {}) {
  const response = await fetch(path, options);
  const text = await response.text();
  let payload = null;
  if (text) {
    try { payload = JSON.parse(text); } catch { payload = text; }
  }
  if (!response.ok) throw new Error(payload?.detail || payload?.error || response.statusText);
  return payload;
}
function parseRoute() {
  const hash = window.location.hash || '#/jobs';
  const normalized = hash.startsWith('#') ? hash.slice(1) : hash;
  const [pathPart, queryString = ''] = normalized.split('?');
  return { segments: pathPart.split('/').filter(Boolean), query: new URLSearchParams(queryString) };
}
function navigate(hash) { window.location.hash = hash; }
function renderLoading(message = 'Loading…') { appRoot.innerHTML = `<div class="loading-state">${escapeHtml(message)}</div>`; }
function renderError(message) { appRoot.innerHTML = `<div class="error-state">${escapeHtml(message)}</div>`; }
function activateNav() {
  document.querySelectorAll('.nav-links a').forEach((link) => {
    link.classList.toggle('active', link.getAttribute('href') === '#/jobs');
  });
}
function formatDate(value) {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}
function decisionBadge(decision) { return badge(decision?.replaceAll('_', ' ') || 'unevaluated', `decision-${decision}`); }
function stageBadge(stage) { return badge(stage?.replaceAll('_', ' ') || 'unknown', 'stage'); }
function candidateCardMarkup(candidate) {
  const latest = candidate.latest_evaluation;
  const strengths = latest?.explainability?.top_strengths || [];
  const risks = latest?.explainability?.top_risks || [];
  const moveOptions = stages
    .filter((stage) => stage !== candidate.current_stage)
    .map(
      (stage) =>
        `<button type="button" class="stage-option" data-action="move-stage-to" data-job-id="${candidate.job_id}" data-candidate-id="${candidate.candidate_id}" data-target-stage="${stage}">${escapeHtml(stage.replaceAll('_', ' '))}</button>`,
    )
    .join('');
  return `
    <article class="candidate-card">
      <div class="split-header">
        <div><h3>${escapeHtml(candidate.name)}</h3><div class="meta-row">${escapeHtml(candidate.filename)}</div></div>
        <div class="badge-row">${stageBadge(candidate.current_stage)}${decisionBadge(latest?.decision || 'unevaluated')}${candidate.shortlist_status ? badge('shortlist', 'shortlist') : ''}${candidate.conflict_analysis?.has_conflict ? badge('conflict', 'conflict') : ''}</div>
      </div>
      <div class="metric-grid">
        <div class="metric"><span class="metric-label">Fit score</span><strong>${escapeHtml(latest?.fit_score ?? '—')}</strong></div>
        <div class="metric"><span class="metric-label">Top strengths</span><strong>${escapeHtml(strengths.slice(0, 2).join(', ') || '—')}</strong></div>
        <div class="metric"><span class="metric-label">Top risks</span><strong>${escapeHtml(risks.slice(0, 2).join(', ') || '—')}</strong></div>
      </div>
      <div class="inline-actions">
        <button data-action="open-candidate" data-job-id="${candidate.job_id}" data-candidate-id="${candidate.candidate_id}">Open detail</button>
        <details class="stage-menu">
          <summary class="secondary">Move stage</summary>
          <div class="stage-menu-panel">
            ${moveOptions || '<div class="stage-menu-empty">No other stages available.</div>'}
          </div>
        </details>
        <button class="ghost" data-action="shortlist-toggle" data-job-id="${candidate.job_id}" data-candidate-id="${candidate.candidate_id}">${candidate.shortlist_status ? 'Remove shortlist' : 'Add shortlist'}</button>
      </div>
    </article>`;
}async function loadCandidateDetails(jobId) {
  const list = await api(`/jobs/${jobId}/candidates`);
  return Promise.all(list.items.map((item) => api(`/jobs/${jobId}/candidates/${item.candidate_id}`)));
}
async function renderJobsPage() {
  setTitle('Jobs');
  renderLoading('Loading jobs…');
  const jobs = await api('/jobs');
  appRoot.innerHTML = `
    <section class="grid two">
      <div class="panel">
        <div class="panel-header"><div><p class="eyebrow">Hiring positions</p><h3>Open jobs</h3></div></div>
        <div class="grid two">
          ${jobs.length ? jobs.map((job) => `
            <article class="card">
              <div class="card-header">
                <div><h3>${escapeHtml(job.title)}</h3><div class="meta-row">${escapeHtml(job.department)}</div></div>
                <div class="badge-row">${badge(job.status || 'open')}${badge(`${job.candidate_count} candidates`)}</div>
              </div>
              <div class="meta-row">Created ${escapeHtml(formatDate(job.created_at))}</div>
              <div class="inline-actions"><button data-action="open-job" data-job-id="${job.job_id}">Open pipeline</button></div>
            </article>`).join('') : '<div class="empty-state">No jobs yet. Create the first job to start screening.</div>'}
        </div>
      </div>
      <div class="panel">
        <div class="panel-header"><div><p class="eyebrow">Create job</p><h3>New hiring workflow</h3></div></div>
        <form id="create-job-form" class="stack">
          <div class="form-grid">
            <label><span class="muted">Title</span><input name="title" required></label>
            <label><span class="muted">Department</span><input name="department" required></label>
          </div>
          <label><span class="muted">评分模板（可留空）</span><input name="department_profile" placeholder="例如 backend_engineering；不填就按通用方式处理"></label>
          <label><span class="muted">Job description</span><textarea name="jd_text" required></textarea></label>
          <label><span class="muted">Department preferences (optional)</span><textarea name="default_department_preference_input" placeholder="可以直接输入：比如 偏好有招聘经验、沟通强、稳定性好"></textarea></label>
          <label><span class="muted">Department rules override (optional)</span><textarea name="department_rules_yaml" placeholder="通常留空即可；只有你想自定义整套部门规则时再填写"></textarea></label>
          <div class="form-actions"><button type="submit">Create job</button></div>
        </form>
      </div>
    </section>`;

  document.getElementById('create-job-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const formElement = event.currentTarget;
    const submitButton = formElement.querySelector('button[type="submit"]');
    const originalLabel = submitButton.textContent;
    submitButton.disabled = true;
    submitButton.textContent = 'Creating...';
    try {
      const form = new FormData(formElement);
      const body = Object.fromEntries(form.entries());
      Object.keys(body).forEach((key) => {
        if (typeof body[key] === 'string') body[key] = body[key].trim();
      });
      if (!body.department_profile) delete body.department_profile;
      if (!body.default_department_preference_input) delete body.default_department_preference_input;
      if (!body.department_rules_yaml) delete body.department_rules_yaml;
      const job = await api('/jobs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      setStatus('Job created successfully.');
      navigate(`#/jobs/${job.job_id}`);
    } catch (error) {
      setStatus(error.message || 'Job creation failed.', 'error');
    } finally {
      submitButton.disabled = false;
      submitButton.textContent = originalLabel;
      submitButton.classList.remove('loading-dots');
    }
  });
}
async function renderJobDetail(jobId) {
  setTitle('Job pipeline');
  renderLoading('Loading job pipeline…');
  const [job, candidates, shortlist] = await Promise.all([api(`/jobs/${jobId}`), loadCandidateDetails(jobId), api(`/jobs/${jobId}/shortlist`)]);
  const grouped = Object.fromEntries(stages.map((stage) => [stage, candidates.filter((candidate) => candidate.current_stage === stage)]));
  appRoot.innerHTML = `
    <section class="stack">
      <div class="panel">
        <div class="split-header">
          <div><p class="eyebrow">Job detail</p><h3>${escapeHtml(job.title)}</h3><div class="meta-row">${escapeHtml(job.department)} · ${escapeHtml(job.status)} · Created ${escapeHtml(formatDate(job.created_at))}</div></div>
          <div class="toolbar"><button data-action="generate-shortlist" data-job-id="${job.job_id}">Generate shortlist</button><button class="secondary" data-action="open-compare" data-job-id="${job.job_id}">Compare candidates</button></div>
        </div>
        <div class="metric-grid"><div class="metric"><span class="metric-label">Candidates</span><strong>${job.candidate_count}</strong></div><div class="metric"><span class="metric-label">Shortlist</span><strong>${job.shortlist_count}</strong></div></div>
      </div>
      <section class="grid two">
        <div class="panel">
          <div class="panel-header"><div><p class="eyebrow">Add candidate</p><h3>Upload resume</h3></div></div>
          <form id="add-candidate-form" class="stack">
            <div class="form-grid"><label><span class="muted">Name</span><input name="name"></label><label><span class="muted">Source</span><input name="source" placeholder="Referral, inbound, agency"></label></div>
            <div class="form-grid"><label><span class="muted">Stage</span><select name="current_stage">${stages.map((stage) => `<option value="${stage}">${stage.replaceAll('_', ' ')}</option>`).join('')}</select></label><label><span class="muted">Resume PDF</span><input type="file" name="resume" accept="application/pdf" required></label></div>
            <div class="form-actions"><button type="submit">Add candidate</button></div>
          </form>
        </div>
        <div class="panel">
          <div class="panel-header"><div><p class="eyebrow">Shortlist</p><h3>Recruiter recommendations</h3></div></div>
          <div class="list">
            ${shortlist.items.length ? shortlist.items.map((entry) => `
              <div class="list-item">
                <div class="split-header"><div><strong>${escapeHtml(entry.candidate_id)}</strong><div class="meta-row">${escapeHtml(entry.explainability_summary || 'No summary yet')}</div></div><div class="badge-row">${stageBadge(entry.current_stage)}${decisionBadge(entry.decision)}${entry.conflict_indicator ? badge('conflict', 'conflict') : ''}</div></div>
                <div class="inline-actions"><input type="number" min="1" value="${escapeHtml(entry.shortlist_priority ?? '')}" data-priority-input="${entry.candidate_id}" placeholder="Priority"><button class="secondary" data-action="update-shortlist-priority" data-job-id="${jobId}" data-candidate-id="${entry.candidate_id}">Save priority</button><button class="danger" data-action="remove-shortlist" data-job-id="${jobId}" data-candidate-id="${entry.candidate_id}">Remove</button></div>
              </div>`).join('') : '<div class="empty-state">No shortlist entries yet.</div>'}
          </div>
        </div>
      </section>
      <section class="kanban">
        ${stages.map((stage) => `
          <div class="stage-column">
            <div class="split-header"><div><p class="eyebrow">Stage</p><h3>${escapeHtml(stage.replaceAll('_', ' '))}</h3></div><button class="ghost" data-action="compare-stage" data-job-id="${jobId}" data-stage="${stage}" ${stage === 'initial_screen' ? 'disabled' : ''}>Compare</button></div>
            ${grouped[stage].length ? grouped[stage].map(candidateCardMarkup).join('') : '<div class="empty-state">No candidates in this stage.</div>'}
          </div>`).join('')}
      </section>
    </section>`;
  document.getElementById('add-candidate-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const formElement = event.currentTarget;
    const submitButton = formElement.querySelector('button[type="submit"]');
    const originalLabel = submitButton.textContent;
    submitButton.disabled = true;
    submitButton.textContent = 'Adding';
    submitButton.classList.add('loading-dots');
    try {
      const formData = new FormData(formElement);
      await api(`/jobs/${jobId}/candidates`, { method: 'POST', body: formData });
      setStatus('Candidate added to the job pipeline.');
      await renderJobDetail(jobId);
    } catch (error) {
      setStatus(error.message || 'Candidate upload failed.', 'error');
    } finally {
      submitButton.disabled = false;
      submitButton.textContent = originalLabel;
      submitButton.classList.remove('loading-dots');
    }
  });
}
function explainabilitySection(explainability = {}) {
  return `
    <div class="grid two">
      <div class="panel"><div class="panel-header"><h3>Why recommended</h3></div><div class="list">${sectionList((explainability.why_recommended || []).map((item) => `${escapeHtml(item.label)}: ${escapeHtml(item.detail)}`), 'No positive rationale recorded.')}</div></div>
      <div class="panel"><div class="panel-header"><h3>Why not recommended</h3></div><div class="list">${sectionList((explainability.why_not_recommended || []).map((item) => `${escapeHtml(item.label)}: ${escapeHtml(item.detail)}`), 'No blockers recorded.')}</div></div>
      <div class="panel"><div class="panel-header"><h3>Strengths and risks</h3></div><div class="list">${sectionList((explainability.top_strengths || []).map((item) => `Strength: ${escapeHtml(item)}`), 'No strengths yet.')}${sectionList((explainability.top_risks || []).map((item) => `Risk: ${escapeHtml(item)}`), 'No risks yet.')}</div></div>
      <div class="panel"><div class="panel-header"><h3>Transferable rationale and sources</h3></div><div class="list">${sectionList((explainability.transferable_skill_rationale || []).map((item) => escapeHtml(item)), 'No transferable skill rationale yet.')}${sectionList((explainability.evidence_sources || []).map((item) => `${escapeHtml(item.source_type)}: ${escapeHtml(item.detail)}`), 'No evidence sources recorded.')}</div></div>
    </div>`;
}
async function renderCandidateDetail(jobId, candidateId) {
  setTitle('Candidate detail');
  renderLoading('Loading candidate detail…');
  const [candidate, feedback] = await Promise.all([api(`/jobs/${jobId}/candidates/${candidateId}`), api(`/jobs/${jobId}/candidates/${candidateId}/feedback`)]);
  const latest = candidate.latest_evaluation;
  const scorecard = latest?.scorecard || {};
  appRoot.innerHTML = `
    <section class="stack">
      <div class="panel">
        <div class="split-header"><div><p class="eyebrow">Candidate</p><h3>${escapeHtml(candidate.name)}</h3><div class="meta-row">${escapeHtml(candidate.filename)} · Added ${escapeHtml(formatDate(candidate.created_at))}</div></div><div class="badge-row">${stageBadge(candidate.current_stage)}${latest ? decisionBadge(latest.decision) : badge('unevaluated')}${candidate.shortlist_status ? badge('shortlist', 'shortlist') : ''}${candidate.conflict_analysis?.has_conflict ? badge('conflict', 'conflict') : ''}</div></div>
        <div class="toolbar"><button data-action="back-job" data-job-id="${jobId}">Back to pipeline</button></div>
      </div>
      <div class="split">
        <div class="stack">
          <div class="panel">
            <div class="panel-header"><h3>Latest evaluation</h3></div>
            ${latest ? `
              <div class="metric-grid"><div class="metric"><span class="metric-label">Fit score</span><strong>${latest.fit_score}</strong></div><div class="metric"><span class="metric-label">JD match</span><strong>${scorecard.jd_match_score ?? 0}</strong></div><div class="metric"><span class="metric-label">Dept preference</span><strong>${scorecard.department_preference_score ?? 0}</strong></div><div class="metric"><span class="metric-label">Interview</span><strong>${scorecard.interview_feedback_score ?? 0}</strong></div><div class="metric"><span class="metric-label">Transferable</span><strong>${scorecard.transferable_skill_score ?? 0}</strong></div></div>
              <div class="list">
                <div class="list-item"><strong>Summary</strong><div class="meta-row">${escapeHtml(latest.summary || 'No summary')}</div></div>
                <div class="list-item"><strong>Matched requirements</strong>${sectionList((latest.matched_requirements || []).map((item) => `${escapeHtml(item.requirement)} (${escapeHtml(item.score)})`), 'No matches recorded.')}</div>
                <div class="list-item"><strong>Missing requirements</strong>${sectionList((latest.missing_requirements || []).map((item) => `${escapeHtml(item.requirement)}: ${escapeHtml(item.reason)}`), 'No missing requirements recorded.')}</div>
                <div class="list-item"><strong>Risk flags</strong>${sectionList((latest.risk_flags || []).map((item) => `${escapeHtml(item.category)}: ${escapeHtml(item.message)}`), 'No risk flags recorded.')}</div>
                <div class="list-item"><strong>Transferable skills</strong>${sectionList((latest.transferable_skills || []).map((item) => `${escapeHtml(item.jd_skill)} ← ${escapeHtml(item.candidate_skill || 'none')} (${escapeHtml(item.relationship)})`), 'No transferable skill notes recorded.')}</div>
                <div class="list-item"><strong>Evidence</strong>${sectionList((latest.evidence || []).map((item) => `${escapeHtml(item.section_label)} · ${escapeHtml(item.matched_jd_item)} · ${escapeHtml(item.matched_resume_snippet)}`), 'No evidence recorded.')}</div>
              </div>` : '<div class="empty-state">No stage evaluation yet.</div>'}
          </div>
          ${latest ? explainabilitySection(latest.explainability) : ''}
        </div>
        <div class="stack">
          <div class="panel">
            <div class="panel-header"><h3>Actions</h3></div>
            <form id="stage-form" class="stack"><label><span class="muted">Move to stage</span><select name="target_stage">${stages.map((stage) => `<option value="${stage}" ${candidate.current_stage === stage ? 'selected' : ''}>${stage.replaceAll('_', ' ')}</option>`).join('')}</select></label><div class="form-actions"><button type="submit">Update stage</button></div></form>
            <form id="evaluation-form" class="stack"><label><span class="muted">Evaluate stage</span><select name="stage">${stages.map((stage) => `<option value="${stage}" ${candidate.current_stage === stage ? 'selected' : ''}>${stage.replaceAll('_', ' ')}</option>`).join('')}</select></label><label><span class="muted">Interview notes (optional)</span><textarea name="interview_notes_text"></textarea></label><div class="form-actions"><button type="submit">Run stage evaluation</button></div></form>
            <div class="inline-actions"><button class="ghost" data-action="shortlist-toggle" data-job-id="${jobId}" data-candidate-id="${candidateId}">${candidate.shortlist_status ? 'Remove shortlist' : 'Add shortlist'}</button></div>
          </div>
          <div class="panel">
            <div class="panel-header"><h3>Interview feedback</h3></div>
            <form id="feedback-form" class="stack"><div class="form-grid"><label><span class="muted">Interviewer name</span><input name="interviewer_name" required></label><label><span class="muted">Stage</span><select name="stage"><option value="first_round">first round</option><option value="second_round">second round</option></select></label></div><label><span class="muted">Raw notes</span><textarea name="raw_notes" required></textarea></label><div class="form-actions"><button type="submit">Submit feedback</button></div></form>
            <div class="list">${feedback.items.length ? feedback.items.map((item) => `<div class="list-item"><strong>${escapeHtml(item.interviewer_name)}</strong><div class="meta-row">${escapeHtml(item.stage)} · ${escapeHtml(item.recommendation)} · ${escapeHtml(formatDate(item.submitted_at))}</div><div class="meta-row">${escapeHtml(item.raw_notes)}</div></div>`).join('') : '<div class="empty-state">No feedback submitted yet.</div>'}</div>
          </div>
          <div class="panel"><div class="panel-header"><h3>Aggregated feedback</h3></div><div class="list">${feedback.aggregates.length ? feedback.aggregates.map((item) => `<div class="list-item"><strong>${escapeHtml(item.stage)}</strong><div class="meta-row">${escapeHtml(item.summary)}</div>${item.conflict_analysis?.has_conflict ? `<div class="tag-row">${badge('conflict', 'conflict')}</div>` : ''}</div>`).join('') : '<div class="empty-state">No aggregate feedback available yet.</div>'}</div></div>
        </div>
      </div>
    </section>`;
  document.getElementById('stage-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const body = Object.fromEntries(new FormData(event.currentTarget).entries());
    await api(`/jobs/${jobId}/candidates/${candidateId}/stage`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    setStatus('Candidate stage updated.');
    await renderCandidateDetail(jobId, candidateId);
  });
  document.getElementById('evaluation-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const body = Object.fromEntries(new FormData(event.currentTarget).entries());
    await api(`/jobs/${jobId}/candidates/${candidateId}/evaluate`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    setStatus('Stage evaluation completed.');
    await renderCandidateDetail(jobId, candidateId);
  });
  document.getElementById('feedback-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const body = Object.fromEntries(new FormData(event.currentTarget).entries());
    await api(`/jobs/${jobId}/candidates/${candidateId}/feedback`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    setStatus('Interview feedback submitted.');
    await renderCandidateDetail(jobId, candidateId);
  });
}
async function renderComparisonPage(jobId, stage = 'first_round') {
  setTitle('Candidate comparison');
  renderLoading('Loading comparison workspace…');
  const [job, candidates] = await Promise.all([api(`/jobs/${jobId}`), loadCandidateDetails(jobId)]);
  const stageCandidates = candidates.filter((candidate) => candidate.current_stage === stage);
  appRoot.innerHTML = `
    <section class="stack">
      <div class="panel">
        <div class="split-header"><div><p class="eyebrow">Comparison</p><h3>${escapeHtml(job.title)}</h3><div class="meta-row">Compare same-stage candidates for recruiter and hiring-manager review.</div></div><div class="toolbar"><button data-action="back-job" data-job-id="${jobId}">Back to pipeline</button></div></div>
        <form id="compare-form" class="stack">
          <label><span class="muted">Stage</span><select name="stage">${['first_round', 'second_round'].map((value) => `<option value="${value}" ${stage === value ? 'selected' : ''}>${value.replaceAll('_', ' ')}</option>`).join('')}</select></label>
          <div class="list">${stageCandidates.length ? stageCandidates.map((candidate) => `<label class="list-item"><input type="checkbox" name="candidate_ids" value="${candidate.candidate_id}"> <strong>${escapeHtml(candidate.name)}</strong> <span class="meta-row">${escapeHtml(candidate.filename)}</span></label>`).join('') : '<div class="empty-state">No candidates in this stage yet.</div>'}</div>
          <div class="form-actions"><button type="submit">Compare selected candidates</button></div>
        </form>
      </div>
      <div id="comparison-results"></div>
    </section>`;
  document.getElementById('compare-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const formElement = event.currentTarget;
    const submitButton = formElement.querySelector('button[type="submit"]');
    const originalLabel = submitButton.textContent;
    const form = new FormData(formElement);
    const selected = form.getAll('candidate_ids');
    const compareStage = form.get('stage');
    if (selected.length < 2) {
      setStatus('Please select at least two candidates to compare.', 'error');
      return;
    }
    submitButton.disabled = true;
    submitButton.textContent = 'Comparing';
    submitButton.classList.add('loading-dots');
    try {
      setStatus('Building candidate comparison. This can take a few seconds.');
      const result = await api(`/jobs/${jobId}/compare`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ candidate_ids: selected, stage: compareStage }) });
      document.getElementById('comparison-results').innerHTML = `
        <div class="panel"><div class="panel-header"><div><p class="eyebrow">Summary</p><h3>Comparative takeaways</h3></div></div><div class="list">${sectionList((result.comparative_summary || []).map((item) => escapeHtml(item)), 'No comparison summary yet.')}</div></div>
        <div class="comparison-grid">${result.comparisons.map((item) => `
          <article class="card">
            <div class="card-header"><div><h3>${escapeHtml(item.name)}</h3><div class="meta-row">${escapeHtml(item.filename)}</div></div><div class="badge-row">${decisionBadge(item.decision)}${item.conflict_indicator ? badge('conflict', 'conflict') : ''}</div></div>
            <div class="metric-grid"><div class="metric"><span class="metric-label">Fit score</span><strong>${item.fit_score}</strong></div><div class="metric"><span class="metric-label">JD match</span><strong>${item.scorecard.jd_match_score}</strong></div><div class="metric"><span class="metric-label">Interview</span><strong>${item.scorecard.interview_feedback_score}</strong></div></div>
            <div class="list">
              <div class="list-item"><strong>Top matches</strong>${sectionList((item.top_matched_requirements || []).map((match) => `${escapeHtml(match.requirement)} (${escapeHtml(match.score)})`))}</div>
              <div class="list-item"><strong>Top gaps</strong>${sectionList((item.top_missing_requirements || []).map((gap) => `${escapeHtml(gap.requirement)}: ${escapeHtml(gap.reason)}`))}</div>
              <div class="list-item"><strong>Top risks</strong>${sectionList((item.top_risks || []).map((risk) => `${escapeHtml(risk.category)}: ${escapeHtml(risk.message)}`))}</div>
              <div class="list-item"><strong>Transferable skills</strong>${sectionList((item.transferable_skill_highlights || []).map((skill) => `${escapeHtml(skill.jd_skill)} ← ${escapeHtml(skill.candidate_skill || 'none')} (${escapeHtml(skill.relationship)})`), 'No transferable highlights.')}</div>
              <div class="list-item"><strong>Interview summary</strong><div class="meta-row">${escapeHtml(item.interview_feedback_summary || 'No interview summary')}</div></div>
              <div class="list-item"><strong>Explainability</strong><div class="meta-row">${escapeHtml(item.explainability_summary || 'No explainability summary')}</div></div>
            </div>
          </article>`).join('')}</div>`;
      setStatus('Candidate comparison ready.');
    } catch (error) {
      setStatus(error.message || 'Candidate comparison failed.', 'error');
    } finally {
      submitButton.disabled = false;
      submitButton.textContent = originalLabel;
      submitButton.classList.remove('loading-dots');
    }
  });
}
async function handleClick(event) {
  const action = event.target.closest('[data-action]');
  if (!action) return;
  const jobId = action.dataset.jobId;
  const candidateId = action.dataset.candidateId;
  const stage = action.dataset.stage;
  const type = action.dataset.action;
  try {
    if (type === 'open-job') return navigate(`#/jobs/${jobId}`);
    if (type === 'back-job') return navigate(`#/jobs/${jobId}`);
    if (type === 'open-candidate') return navigate(`#/jobs/${jobId}/candidates/${candidateId}`);
    if (type === 'open-compare') return navigate(`#/jobs/${jobId}/compare?stage=first_round`);
    if (type === 'compare-stage') return navigate(`#/jobs/${jobId}/compare?stage=${stage}`);
    if (type === 'generate-shortlist') {
      await api(`/jobs/${jobId}/shortlist/generate`, { method: 'POST' });
      setStatus('Shortlist generated.');
      return renderJobDetail(jobId);
    }
    if (type === 'move-stage-to') {
      const targetStage = action.dataset.targetStage;
      if (!targetStage) return;
      await api(`/jobs/${jobId}/candidates/${candidateId}/stage`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ target_stage: targetStage }) });
      setStatus(`Candidate moved to ${targetStage.replaceAll('_', ' ')}.`);
      return renderJobDetail(jobId);
    }
    if (type === 'shortlist-toggle') {
      const detail = await api(`/jobs/${jobId}/candidates/${candidateId}`);
      if (detail.shortlist_status) {
        await api(`/jobs/${jobId}/shortlist/${candidateId}`, { method: 'DELETE' });
        setStatus('Candidate removed from shortlist.');
      } else {
        await api(`/jobs/${jobId}/shortlist/${candidateId}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ shortlist_priority: null }) });
        setStatus('Candidate added to shortlist.');
      }
      return parseRoute().segments.includes('candidates') ? renderCandidateDetail(jobId, candidateId) : renderJobDetail(jobId);
    }
    if (type === 'remove-shortlist') {
      await api(`/jobs/${jobId}/shortlist/${candidateId}`, { method: 'DELETE' });
      setStatus('Shortlist entry removed.');
      return renderJobDetail(jobId);
    }
    if (type === 'update-shortlist-priority') {
      const input = document.querySelector(`[data-priority-input="${candidateId}"]`);
      const priority = input && input.value ? Number(input.value) : null;
      await api(`/jobs/${jobId}/shortlist/${candidateId}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ shortlist_priority: priority }) });
      setStatus('Shortlist priority updated.');
      return renderJobDetail(jobId);
    }
  } catch (error) {
    setStatus(error.message, 'error');
  }
}
async function render() {
  activateNav();
  const { segments, query } = parseRoute();
  try {
    if (segments.length === 0 || (segments[0] === 'jobs' && segments.length === 1)) return renderJobsPage();
    if (segments[0] === 'jobs' && segments.length === 2) return renderJobDetail(segments[1]);
    if (segments[0] === 'jobs' && segments[2] === 'candidates' && segments.length === 4) return renderCandidateDetail(segments[1], segments[3]);
    if (segments[0] === 'jobs' && segments[2] === 'compare') return renderComparisonPage(segments[1], query.get('stage') || 'first_round');
    renderError('Page not found.');
  } catch (error) {
    setStatus(error.message, 'error');
    renderError(error.message);
  }
}
document.addEventListener('click', handleClick);
window.addEventListener('hashchange', () => { setStatus(''); render(); });
render();






