# voice on iphone

ro takes voice input through an ios shortcut that records audio, posts it
to the api, and reads the response back.

## one-time setup

1. on the mac, make sure the api is reachable from your phone over tailscale. if `ro status` shows api green, you're good.
2. on the iphone, open the shortcuts app.
3. tap the plus to make a new shortcut. add these actions in order:
   - **dictate text** with language set to en-us
   - **get contents of url**, set the url to `http://<your-tailscale-name>:8000/api/voice`, method `post`, request body `form`. add a field named `text` with the dictated text from step 1.
   - **get dictionary value**, key `response`, from the contents of url.
   - **speak text**, value from the previous step.
4. name the shortcut "ro".
5. add it to your home screen, or set it up as the action for the iphone's action button if you have a 15 pro or later.

## what it does

- you speak. the shortcut transcribes locally with apple dictation. that means whisper isn't strictly required for the iphone path. it stays on the api side as a fallback for audio uploads.
- the api hands the text to the supervisor. the response comes back as text.
- the shortcut speaks it.

## privacy

audio never leaves your phone. only the text does. and the api is only reachable from your tailscale network.
