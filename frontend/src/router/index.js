/**
 * Vue Router configuration.
 *
 * This file defines the URL routes for the application -- which component
 * should be displayed when a user navigates to a given URL.
 *
 * Routes:
 *   /               -- Dashboard: set selector, card table, price chart
 *   /cards/:cardId  -- Card detail: price history chart and snapshot table
 */

import { createRouter, createWebHistory } from "vue-router";
import CardDetail from "../views/CardDetail.vue";
import Dashboard from "../views/Dashboard.vue";

// Define the routes. Each object maps a URL path to a component.
const routes = [
  {
    // The root path "/" shows the main dashboard view.
    path: "/",
    component: Dashboard,
  },
  {
    // Card detail page. :cardId is a dynamic segment -- Vue Router makes it
    // available inside the component as route.params.cardId.
    path: "/cards/:cardId",
    component: CardDetail,
  },
];

// Create the router using HTML5 history mode.
// createWebHistory() means URLs look like "/dashboard" rather than the
// hash-based "/#/dashboard" format used in older Vue applications.
export default createRouter({
  history: createWebHistory(),
  routes,
});
