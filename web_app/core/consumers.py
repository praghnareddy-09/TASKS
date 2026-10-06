from channels.generic.websocket import AsyncJsonWebsocketConsumer


class WorkflowConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        user = self.scope["user"]
        if not user.is_authenticated:
            await self.close(code=4401)
            return
        if user.is_admin_role:
            self.group_name = "workflow_admin"
        elif user.is_trainee_role:
            self.group_name = f"workflow_trainee_{user.pk}"
        else:
            await self.close(code=4403)
            return
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        group_name = getattr(self, "group_name", None)
        if group_name:
            await self.channel_layer.group_discard(group_name, self.channel_name)

    async def workflow_changed(self, event):
        await self.send_json({"type": "workflow.changed", "event": event["event"]})
