# mobile access via tailscale

ro lives on the mac. tailscale puts a private network around your devices
so the iphone can reach `localhost:3000` and `localhost:8000` as if they
were on the same wifi.

## setup

1. install tailscale on the mac and the iphone, both signed into the same account.
2. on the mac, open tailscale and copy your machine's tailscale name. it looks like `ro-mbp.tail-scale.ts.net`.
3. on the iphone, open safari to `http://ro-mbp.tail-scale.ts.net:3000`. you should see the ro home page.
4. add to home screen for the pwa shell.

## offline

the pwa caches the shell, so the ui loads without the mac. but the api
isn't reachable, so chat and integrations sit idle until the mac is back online.

## tradeoffs

- one user, one device. multi-user is not in scope.
- if the mac is asleep, no api. set caffeinate or never-sleep on power.
- web push from the mac via vapid still works on iphone over tailscale, you just won't see them when you're off the network.
