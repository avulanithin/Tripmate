function includeHTML(selector, url) {
  fetch(url)
    .then(res => res.text())
    .then(data => {
      document.querySelector(selector).innerHTML = data;
    });
}

document.addEventListener("DOMContentLoaded", function() {
  includeHTML("#navbar-include", "../components/navbar.html");
  includeHTML("#footer-include", "../components/footer.html");
});