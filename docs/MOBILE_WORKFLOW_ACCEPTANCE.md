# Mobile Workflow Acceptance

Use this checklist on phones and small tablets before public launch.

## Student critical flows
- open `Student Portal` home and confirm `Next Actions` is visible without horizontal layout break
- open `Practice CBT`, `Term Results`, `Finance`, and `Notifications`
- verify cards remain tappable and text does not overflow on small screens
- confirm the priority card appears when results are pending or published

## Staff critical flows
- open `Staff Portal` home and confirm `Next Actions` appears above `Quick Access`
- confirm role cards for CBT, results, and approvals are tappable on narrow screens
- verify sidebar/menu remains visible after opening shared routes like CBT and results pages

## IT critical flows
- open `IT Manager Portal` and confirm `Operations Center` is visible on mobile width
- verify portal toggles, runtime snapshot cards, and drill commands remain readable
- confirm sync backlog and disk space cards wrap correctly on narrow screens

## Pressure-test rule
- test with real accounts on a 360px to 430px wide viewport
- no clipped cards, no hidden primary CTA, no trapped horizontal scroll on the page shell
- if any shared workflow page loses the shell or menu context, treat it as a launch blocker
