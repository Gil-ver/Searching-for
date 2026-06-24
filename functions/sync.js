export async function onRequestPost(context) {
  const { request, env } = context;

  try {
    const { path, content } = await request.json();
    
    if (!path || !content) {
      return new Response("❌ 缺少 path 或 content", { status: 400 });
    }

    const url = `https://api.github.com/repos/${env.GH_OWNER}/${env.GH_REPO}/contents/${path}`;
    
    // 获取旧文件 SHA
    const getFile = await fetch(url, {
      headers: {
        "Authorization": `token ${env.GH_TOKEN}`,
        "User-Agent": "CF-Pages-Receiver"
      }
    });

    let sha = undefined;
    if (getFile.ok) {
      const fileData = await getFile.json();
      sha = fileData.sha;
    }

    // 推送给 GitHub
    const putResponse = await fetch(url, {
      method: "PUT",
      headers: {
        "Authorization": `token ${env.GH_TOKEN}`,
        "Content-Type": "application/json",
        "User-Agent": "CF-Pages-Receiver"
      },
      body: JSON.stringify({
        message: `[sync] updated asset via n8n pages pipeline`,
        content: content,
        sha: sha
      })
    });

    if (!putResponse.ok) {
      const errText = await putResponse.text();
      return new Response(`❌ GitHub 拒绝写入: ${errText}`, { status: 500 });
    }

    return new Response(`🎉 [OK] 文件 [${path}] 成功通过 Pages 中转至 GitHub！`, {
      status: 200
    });

  } catch (error) {
    return new Response(`❌ 内部错误: ${error.message}`, { status: 500 });
  }
}