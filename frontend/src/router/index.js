import { createRouter, createWebHistory } from "vue-router";
import Dashboard from "../views/Dashboard.vue";

const routes = [
  {
    path: "/",
    component: Dashboard,
  },
];

export default createRouter({
  history: createWebHistory(),
  routes,
});
