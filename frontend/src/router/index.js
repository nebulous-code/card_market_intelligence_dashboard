import { createRouter, createWebHistory } from "vue-router";
import CardDetail from "../views/CardDetail.vue";
import Dashboard from "../views/Dashboard.vue";

const routes = [
  {
    path: "/",
    redirect: "/sets",
  },
  {
    path: "/sets",
    component: Dashboard,
    meta: {
      breadcrumbs: [
        { title: "Sets", to: "/sets" },
      ],
    },
  },
  {
    path: "/cards/:cardId",
    component: CardDetail,
    meta: {
      breadcrumbs: [
        { title: "Sets", to: "/sets" },
        { title: "Card Detail", to: null },
      ],
    },
  },
];

export default createRouter({
  history: createWebHistory(),
  routes,
});
