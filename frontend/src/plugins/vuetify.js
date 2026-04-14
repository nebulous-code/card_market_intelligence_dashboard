import { createVuetify } from 'vuetify'

export default createVuetify({
  theme: {
    defaultTheme: 'magikarp',
    themes: {
      magikarp: {
        dark: true,
        colors: {
          background:      '#12121F',
          surface:         '#1E1E30',
          primary:         '#E8412A',
          secondary:       '#F5C842',
          error:           '#CF6679',
          success:         '#4CAF82',
          warning:         '#FFA726',
          'on-background': '#F5EDD6',
          'on-surface':    '#F5EDD6',
          'on-primary':    '#F5EDD6',
        },
      },
    },
  },
  icons: {
    defaultSet: 'mdi',
  },
})
