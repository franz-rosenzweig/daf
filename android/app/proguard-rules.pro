# Nothing the page calls by name: the shell talks to it over a message port (Shell.java).

# The home-screen widgets: Glance tells its kinds apart by their class names, so they stay
# themselves. Shrunk, R8 had merged all six into one class and renamed it, and every widget was
# drawn as one kind (Board.drawAll).
-keep class * extends androidx.glance.appwidget.GlanceAppWidget
