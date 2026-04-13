/**
 * Vue Router configuration.
 *
 * This file defines the URL routes for the application -- which component
 * should be displayed when a user navigates to a given URL.
 *
 * For Milestone 1 there is only one route: the dashboard at "/". Additional
 * routes for set detail pages, card detail pages, and other views will be
 * added in later milestones.
 */

import { createRouter, createWebHistory } from "vue-router";
import Dashboard from "../views/Dashboard.vue";

// Define the routes. Each object maps a URL path to a component.
const routes = [
  {
    // The root path "/" shows the main dashboard view.
    path: "/",
    component: Dashboard,
  },
];

// Create the router using HTML5 history mode.
// createWebHistory() means URLs look like "/dashboard" rather than the
// hash-based "/#/dashboard" format used in older Vue applications.
export default createRouter({
  history: createWebHistory(),
  routes,
});
