# SamsungTV Custom - Apps and app IDs

When the TV is on, the integration asks it for the list of installed apps and merges the result into the `media_player`
source list, after the built-in `TV` and `HDMI` entries. Nothing needs to be configured by hand.

## How the list is fetched

The TV is not polled for this. The integration sends a single `get_installed_app` command during startup and the TV
answers with an `ed.installedApp` event carrying a `name` and an `appId` per app. Two consequences worth knowing:

- The list is fetched **once**, when the TV is on at integration start. Apps installed later are not picked up until
  Home Assistant reloads the integration.
- The **legacy protocol (port 55000) never returns an app list** — it has no API for it. On those models the source list
  stays at `TV` and `HDMI`, and that is expected, not a failure.
- The TV is given 3 seconds to answer. Models that ignore the request leave the list empty; the source list then stays at
  `TV` and `HDMI`.

## Launching an app you know the ID of

You do not need the app in the source list to launch it:

```yaml
service: media_player.play_media
data:
  entity_id: media_player.samsung_tv
  media_content_type: app
  media_content_id: "11101200001"
```

## App ID formats

Samsung identifies an app by more than one ID, and both forms work for launching:

- **Numerical ID**, a numeric string — `11101200001` (Netflix), `3201606009684` (Spotify)
- **Alphanumerical ID**, a package name — `org.tizen.netflix-app`, `org.tizen.ignition`

An app normally has both. The numerical ID is the one most published lists collect.

Known lists of app IDs: [List 1](https://github.com/tavicu/homebridge-samsung-tizen/issues/26#issuecomment-447424879),
[List 2](https://github.com/Ape/samsungctl/issues/75#issuecomment-404941201)

If the TV rejects an ID, try the other format for the same app — some apps accept only one of the two.

## Finding an app ID on your own TV

There is no entity attribute that reports the running app, so the integration cannot tell you the ID of an app you
launch by hand. Two practical options:

1. Read the source list in Home Assistant after a restart — apps the TV reported are listed there.
2. Test candidate IDs from a published list with the `media_content_type: app` call above and watch what the TV does.
