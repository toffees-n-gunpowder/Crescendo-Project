from django.shortcuts import render

def home(request):
    # Right now, this just grabs the HTML file and sends it to the user.
    # Later, this is where we will fetch the classical music from your database!
    return render(request, 'music/home.html')