let resultPaths = {};

async function upload() {
  const file = document.getElementById("fileInput").files[0];
  const status = document.getElementById("status");
  const bar = document.getElementById("progressBar");

  if (!file) {
    status.innerText = "Upload ZIP first";
    return;
  }

  const formData = new FormData();
  formData.append("files", file);

  status.innerText = "Uploading...";
  bar.style.width = "10%";

  const res = await fetch("/upload", {
    method: "POST",
    body: formData
  });

  const data = await res.json();

  if (data.error) {
    status.innerText = data.error;
    return;
  }

  resultPaths = data;

  // fake progress
  let progress = 10;
  const interval = setInterval(() => {
    progress += 10;
    bar.style.width = progress + "%";
    status.innerText = "Processing AI...";
    if (progress >= 90) clearInterval(interval);
  }, 2000);

  setTimeout(() => {
    clearInterval(interval);
    bar.style.width = "100%";
    status.innerText = "✅ Done";

    document.getElementById("downloads").style.display = "block";
  }, 12000);
}


// ✅ INSTANT DOWNLOAD
function downloadFile(type) {
  const url = `/download/${type}?path=${encodeURIComponent(resultPaths[type])}`;

  const a = document.createElement("a");
  a.href = url;
  a.setAttribute("download", "");
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
}