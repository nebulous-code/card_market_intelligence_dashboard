<template>
  <!--
    Root application shell.

    v-app is required by Vuetify and must wrap the entire application.
    It sets up the layout system and provides the global theme context
    that all child components inherit.
  -->
  <v-app>
    <!--
      Top navigation bar. color="primary" uses the theme's primary color.
      elevation="2" adds a subtle shadow to visually separate it from the content.
    -->
    <v-app-bar color="primary" elevation="2">
      <v-app-bar-title>
        <!-- Card icon from the Material Design Icons set, followed by the app title. -->
        <v-icon icon="mdi-cards" class="mr-2" />
        Pokemon Card Market Intelligence
      </v-app-bar-title>
    </v-app-bar>

    <!--
      Main content area. router-view renders whichever component the
      current URL maps to. For Milestone 1 this is always Dashboard.vue.
    -->
    <v-main>
      <router-view />
    </v-main>
  </v-app>
</template>
