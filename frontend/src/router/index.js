import { createRouter, createWebHistory } from "vue-router";
import CardDetail from "../views/CardDetail.vue";
import CollectionDashboardView from "../views/CollectionDashboardView.vue";
import CollectionView from "../views/CollectionView.vue";
import DebugLoaderView from "../views/DebugLoaderView.vue";
import NotFoundView from "../views/NotFoundView.vue";
import PrivacyView from "../views/PrivacyView.vue";
import SetDetailView from "../views/SetDetailView.vue";
import SetListView from "../views/SetListView.vue";
import TrendsView from "../views/TrendsView.vue";
import ConditionMultiplierHeatmap from "../views/trends/ConditionMultiplierHeatmap.vue";

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
  {
    path: "/trends/condition-multipliers",
    component: ConditionMultiplierHeatmap,
    meta: {
      breadcrumbs: [
        { title: "Sets", to: "/sets" },
        { title: "Market Trends", to: "/trends" },
        { title: "Condition Multipliers" },
      ],
    },
  },
  {
    path: "/collection",
    component: CollectionView,
    meta: {
      breadcrumbs: [
        { title: "Analyze Your Collection" },
      ],
    },
  },
  {
    path: "/collection/dashboard",
    component: CollectionDashboardView,
    meta: {
      breadcrumbs: [
        { title: "Analyze Your Collection", to: "/collection" },
        { title: "Dashboard" },
      ],
    },
  },
  {
    path: "/privacy",
    component: PrivacyView,
    meta: {
      breadcrumbs: [
        { title: "Privacy Policy" },
      ],
    },
  },
  {
    // Debug harness for the cold-start loader. Not linked from the nav --
    // discoverable via URL only. Mounts ColdStartLoader in debug mode so
    // polling and the error timeout are suppressed.
    path: "/debug/loader",
    component: DebugLoaderView,
    meta: {
      breadcrumbs: [{ title: "Debug" }, { title: "Loader" }],
    },
  },
  {
    // Catch-all. Must stay last -- vue-router matches in order, and a
    // wildcard placed earlier would swallow every route below it.
    //
    // Needed because render.yaml rewrites all paths to index.html so
    // client-side routing survives a refresh. Without this record a
    // mistyped URL renders the nav bar and an empty body.
    path: "/:pathMatch(.*)*",
    component: NotFoundView,
    meta: {
      breadcrumbs: [{ title: "Not Found" }],
    },
  },
];

export default createRouter({
  history: createWebHistory(),
  routes,
});
