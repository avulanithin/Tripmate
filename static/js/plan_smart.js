// static/js/plan_smart.js

function generatePlannerDays(startDate, endDate) {
  const days = [];
  let current = new Date(startDate);
  const end = new Date(endDate);
  let i = 1;
  while (current <= end) {
    days.push(`<div class="planner-day" id="day${i}">
      <h4>Day ${i} (${current.toLocaleDateString()})</h4>
      <ul class="activity-list" id="list${i}"></ul>
    </div>`);
    current.setDate(current.getDate() + 1);
    i++;
  }
  document.getElementById('planner-days').innerHTML = days.join('');
  // Make each activity list sortable
  document.querySelectorAll('.activity-list').forEach(list => {
    new Sortable(list, { group: 'activities', animation: 150 });
  });
}

document.getElementById('trip-form').onsubmit = function(e) {
  e.preventDefault();
  const start = this.start_date.value;
  const end = this.end_date.value;
  generatePlannerDays(start, end);
  // ... any other logic
};