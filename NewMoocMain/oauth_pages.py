"""Self-contained callback pages, with no credentials or external assets."""
from string import Template


_STATES = {
    "success": {
        "title": "登录成功", "tag": "浏览器授权已完成", "eyebrow": "ALL SET",
        "heading": "登录成功。<br><span>回到终端，继续。</span>",
        "description": "登录信息已传回助手，正在验证账号并读取课程。<br>请切换回运行助手的终端窗口，继续选择你的课程。",
        "icon": '<path d="m16 26 7 7 14-15"/>',
        "next_title": "接下来，在终端里操作",
        "next_body": "选择课程，再开始学习管理、题目导出或 AI 答题。",
        "first": "已完成", "second": "下一步", "third": "随后选择",
        "note": "无需复制任何登录信息，也无需在此页面继续操作。",
    },
    "waiting": {
        "title": "等待登录", "tag": "等待浏览器授权", "eyebrow": "READY WHEN YOU ARE",
        "heading": "准备好了。<br><span>完成登录，就出发。</span>",
        "description": "请在已打开的智慧职教登录页完成扫码或短信验证。<br>登录完成后，助手会自动接收结果。",
        "icon": '<circle cx="26" cy="26" r="15"/><path d="M26 16v11l7 4"/>',
        "next_title": "先完成智慧职教登录",
        "next_body": "如果没有看到登录页，请回到终端查看登录提示。",
        "first": "进行中", "second": "登录后返回", "third": "随后选择",
        "note": "保留正在运行的终端窗口，等待授权完成。",
    },
    "error": {
        "title": "登录未完成", "tag": "需要重新登录", "eyebrow": "LET’S TRY AGAIN",
        "heading": "还差一步。<br><span>这次登录没有完成。</span>",
        "description": "没有收到有效的登录信息，助手暂时无法继续。<br>请回到终端重新发起登录，并在新打开的页面完成验证。",
        "icon": '<path d="M26 13v16M26 37v1"/>',
        "next_title": "回到终端，重新登录",
        "next_body": "如果终端仍在等待，可按 Ctrl+C 退出，再重新启动助手。",
        "first": "未完成", "second": "返回重试", "third": "登录后选择",
        "note": "无需手动填写登录凭证。请使用助手打开的登录页面。",
    },
    "not_found": {
        "title": "页面不存在", "tag": "未找到此页面", "eyebrow": "NOT THIS WAY",
        "heading": "走错页面了。<br><span>回到助手，继续。</span>",
        "description": "这个地址不是助手的登录回调页面。<br>请回到终端，按照提示完成登录。",
        "icon": '<path d="M18 18l16 16M34 18 18 34"/>',
        "next_title": "使用助手打开的登录页面",
        "next_body": "不需要手动修改地址或填写登录信息。",
        "first": "等待登录", "second": "返回终端", "third": "登录后选择",
        "note": "此页面可以关闭，不影响终端中的助手。",
    },
}

_PAGE = Template('''<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="referrer" content="no-referrer">
  <title>${title} · ICVE AI Assistant</title>
  <script>
    // The callback query belongs to the local handler, never to the rendered UI.
    try { history.replaceState(null, '', location.pathname); } catch (_) {}
  </script>
  <style>
    :root {
      color-scheme: light; --paper: #f6f7f4; --ink: #203b35; --muted: #667770;
      --accent: #167b60; --mint: #edf5ef; --line: #e1e8df; --white: #fff;
      --font: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
    }
    * { box-sizing: border-box; }
    body { margin: 0; min-height: 100vh; font-family: var(--font); color: var(--ink); background: var(--paper); }
    body::before { content: ""; position: fixed; inset: 0; pointer-events: none; opacity: .38;
      background-image: radial-gradient(#a7b8a6 .7px, transparent .7px); background-size: 20px 20px; }
    .page { position: relative; min-height: 100vh; max-width: 1280px; margin: auto; padding: 36px 56px 24px;
      display: flex; flex-direction: column; }
    header { display: flex; align-items: center; justify-content: space-between; gap: 24px; }
    .brand { display: flex; align-items: center; gap: 12px; }
    .brand-mark { width: 36px; height: 36px; border-radius: 11px; background: var(--ink); display: grid; place-items: center; color: #d5edc9; }
    .brand-title { font-size: 15px; font-weight: 650; letter-spacing: -.2px; }
    .brand-subtitle { display: block; margin-top: 3px; font-size: 11px; color: var(--muted); letter-spacing: 1.2px; }
    .header-label { font-size: 12px; color: var(--muted); display: flex; align-items: center; gap: 8px; }
    .header-label::before { content: ""; width: 5px; height: 5px; background: #93a392; border-radius: 50%; }
    main { flex: 1; width: 100%; display: grid; align-content: center; padding: 64px 0; }
    .card { width: 100%; max-width: 960px; margin: auto; display: grid; grid-template-columns: 254px minmax(0, 1fr);
      background: var(--white); border: 1px solid var(--line); border-radius: 24px; overflow: hidden;
      box-shadow: 0 12px 42px -20px #25463520; }
    aside { background: var(--mint); padding: 38px 30px; display: flex; flex-direction: column; }
    .aside-label { margin: 0; font-size: 11px; letter-spacing: 2px; font-weight: 600; color: #728a7b; }
    .aside-title { margin: 12px 0 38px; font-size: 22px; line-height: 1.5; font-weight: 600; letter-spacing: -.5px; }
    .steps { list-style: none; padding: 0; margin: 0; }
    .steps li { position: relative; display: flex; gap: 13px; padding-bottom: 30px; }
    .steps li:not(:last-child)::after { content: ""; position: absolute; left: 14px; top: 36px; bottom: 7px; width: 1px; background: #ceded1; }
    .step-number { flex: 0 0 30px; width: 30px; height: 30px; border-radius: 50%; border: 1px solid #c6d6c9;
      display: grid; place-items: center; font-size: 11px; font-weight: 600; color: #6e8978; background: var(--mint); }
    .step-done .step-number { color: white; background: var(--accent); border-color: var(--accent); }
    .steps strong { display: block; font-size: 13px; font-weight: 550; margin: 0 0 6px; }
    .steps small { font-size: 11px; color: #73887a; }
    .aside-footer { margin-top: auto; padding-top: 30px; border-top: 1px solid #d7e4d8; color: #728579; font-size: 11px; line-height: 1.8; }
    .content { padding: 44px 48px 38px; }
    .status-row { display: flex; align-items: center; justify-content: space-between; gap: 20px; }
    .hero-icon { width: 64px; height: 64px; display: grid; place-items: center; background: #edf7ee; color: var(--accent); border-radius: 20px; }
    .hero-icon svg { width: 48px; height: 48px; stroke: currentColor; stroke-width: 2.5; fill: none; stroke-linecap: round; stroke-linejoin: round; }
    .tag { display: inline-flex; align-items: center; gap: 7px; border: 1px solid #dbe9dc; border-radius: 99px;
      color: #54795f; font-size: 11px; padding: 7px 10px; white-space: nowrap; }
    .tag::before { content: ""; width: 5px; height: 5px; border-radius: 50%; background: #66a17b; }
    .eyebrow { margin: 32px 0 12px; font-size: 10px; font-weight: 650; letter-spacing: 2.2px; color: #839184; }
    h1 { margin: 0; font-size: clamp(28px, 3.3vw, 38px); font-weight: 650; line-height: 1.5; letter-spacing: -1.4px; }
    h1 span { color: #587263; }
    .description { margin: 18px 0 28px; font-size: 13px; color: var(--muted); line-height: 1.9; }
    .next { display: flex; align-items: center; gap: 14px; border-top: 1px solid var(--line); border-bottom: 1px solid var(--line); padding: 20px 0; }
    .terminal-icon { flex-shrink: 0; width: 36px; height: 36px; display: grid; place-items: center; color: #5b7564;
      border: 1px solid #e1e8df; border-radius: 9px; background: #f8faf7; }
    .next strong { display: block; font-size: 13px; font-weight: 600; margin-bottom: 6px; }
    .next p { margin: 0; color: var(--muted); font-size: 11px; line-height: 1.8; }
    .actions { display: flex; align-items: center; gap: 18px; margin-top: 26px; }
    button { display: inline-flex; align-items: center; justify-content: center; gap: 22px; font-family: inherit; font-size: 13px;
      background: var(--ink); color: white; border: 0; padding: 13px 18px; border-radius: 10px; cursor: pointer; transition: background .15s; }
    button:hover { background: var(--accent); }
    button:focus-visible { outline: 3px solid #7db99e; outline-offset: 4px; }
    .actions span { color: #849187; font-size: 11px; }
    .close-help { font-size: 12px; color: var(--muted); line-height: 1.8; margin: 14px 0 0; }
    .note { max-width: 960px; margin: 20px auto 0; color: #78877b; font-size: 11px; text-align: center; line-height: 1.8; }
    footer { display: flex; justify-content: space-between; gap: 12px; color: #859086; font-size: 10px; letter-spacing: .3px; }
    .error .hero-icon, .not_found .hero-icon { background: #fcf3e8; color: #986636; }
    .error .tag, .not_found .tag { color: #8f6b42; border-color: #ecdfcc; }
    .error .tag::before, .not_found .tag::before { background: #b78a55; }
    @media (max-width: 760px) {
      .page { padding: 24px; } main { padding: 40px 0; } .card { grid-template-columns: 1fr; }
      aside { padding: 22px 26px; } .aside-label, .aside-title, .aside-footer { display: none; }
      .steps { display: flex; justify-content: space-between; gap: 12px; } .steps li { padding: 0; gap: 8px; align-items: center; }
      .steps li::after { display: none; } .steps strong { font-size: 11px; margin-bottom: 4px; }
      .steps small { font-size: 10px; } .step-number { flex-basis: 24px; width: 24px; height: 24px; font-size: 10px; }
      .content { padding: 30px; } h1 { font-size: 32px; } .header-label { display: none; }
    }
    @media (max-width: 420px) {
      .page { padding: 22px 16px; } main { padding: 28px 0; } aside { padding: 18px 14px; }
      .content { padding: 26px 22px; } h1 { font-size: 28px; } .description br { display: none; }
      .hero-icon { width: 54px; height: 54px; border-radius: 16px; } .tag { font-size: 10px; padding: 6px 8px; }
      .actions { gap: 12px; } .actions span { font-size: 10px; } footer { flex-wrap: wrap; }
    }
    @media (prefers-reduced-motion: reduce) { button { transition: none; } }
  </style>
</head>
<body class="${state}">
  <div class="page">
    <header>
      <div class="brand">
        <div class="brand-mark" aria-hidden="true"><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M4 5h6l2 2 2-2h6v14h-6l-2 2-2-2H4zM12 7v14"/></svg></div>
        <div class="brand-title">ICVE AI Assistant<span class="brand-subtitle">智慧职教助手</span></div>
      </div>
      <div class="header-label">浏览器授权</div>
    </header>
    <main>
      <section class="card" aria-labelledby="heading">
        <aside aria-label="操作步骤">
          <p class="aside-label">YOUR NEXT CHAPTER</p>
          <h2 class="aside-title">从这里，<br>继续你的课程。</h2>
          <ol class="steps">
            <li class="${first_class}"><span class="step-number" aria-hidden="true">01</span><div><strong>登录账号</strong><small>${first}</small></div></li>
            <li><span class="step-number" aria-hidden="true">02</span><div><strong>返回终端</strong><small>${second}</small></div></li>
            <li><span class="step-number" aria-hidden="true">03</span><div><strong>选择课程</strong><small>${third}</small></div></li>
          </ol>
          <div class="aside-footer">学习管理 · 题目导出 · AI 答题<br>在一个助手里，完成下一步。</div>
        </aside>
        <div class="content">
          <div class="status-row"><div class="hero-icon" aria-hidden="true"><svg viewBox="0 0 52 52">${icon}</svg></div><span class="tag">${tag}</span></div>
          <p class="eyebrow">${eyebrow}</p>
          <h1 id="heading">${heading}</h1>
          <p class="description">${description}</p>
          <div class="next">
            <div class="terminal-icon" aria-hidden="true"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="m5 7 5 5-5 5M13 17h6"/></svg></div>
            <div><strong>${next_title}</strong><p>${next_body}</p></div>
          </div>
          <div class="actions"><button type="button" id="close-page">关闭此页 <svg aria-hidden="true" width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4"><path d="m6 3 5 5-5 5M1 8h10"/></svg></button><span>也可以直接关闭这个标签页</span></div>
          <p id="close-help" class="close-help" role="status" aria-live="polite" hidden></p>
          <noscript><p class="close-help">请手动关闭此标签页，然后返回终端。</p></noscript>
        </div>
      </section>
      <p class="note">${note}</p>
    </main>
    <footer><span>ICVE AI ASSISTANT</span><span>你的课程，接着来。</span></footer>
  </div>
  <script>
    document.getElementById('close-page').addEventListener('click', function () {
      const help = document.getElementById('close-help');
      help.hidden = false;
      help.textContent = '如果页面没有关闭，请手动关闭此标签页，然后切换回终端窗口。';
      window.close();
    });
  </script>
</body>
</html>
''')


def render_oauth_page(state):
    """Only fixed state copy is interpolated; tokens are never template inputs."""
    return _PAGE.substitute(_STATES[state], state=state,
                            first_class="step-done" if state == "success" else "")
