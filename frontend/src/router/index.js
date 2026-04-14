import { createRouter, createWebHistory } from "vue-router";
import CardDetail from "../views/CardDetail.vue";
import SetDetailView from "../views/SetDetailView.vue";
import SetListView from "../views/SetListView.vue";
import TrendsView from "../views/TrendsView.vue";

const routes = [
  {
    path: "/",
    redirect: "/sets",
  },
  {
    path: "/sets",
    component: SetListView,
    meta: {
      breadcrumbs: [
        { title: "Sets" },
      ],
    },
  },
  {
    path: "/sets/:setId",
    component: SetDetailView,
    meta: {
      breadcrumbs: [
        { title: "Sets", to: "/sets" },
        { title: ":setId" }, // replaced dynamically by the view
      ],
    },
  },
  {
    path: "/cards/:cardId",
    component: CardDetail,
    meta: {
      breadcrumbs: [
        { title: "Sets", to: "/sets" },
        { title: ":setId", to: "/sets/:setId" }, // replaced dynamically
        { title: ":cardId" },                     // replaced dynamically
      ],
    },
  },
  {
    path: "/trends",
    component: TrendsView,
    meta: {
      breadcrumbs: [
        { title: "Sets", to: "/sets" },
        { title: "Market Trends" },
      ],
    },
  },
];

export default createRouter({
  history: createWebHistory(),
  routes,
});
