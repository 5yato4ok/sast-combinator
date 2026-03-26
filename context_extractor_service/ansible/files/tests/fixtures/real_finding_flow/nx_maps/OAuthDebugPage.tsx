export default function OAuthDebugPage() {
  const response = await fetch(`${cloudHost}/oauth/token/`, {
    method: 'POST',
  });
  return response;
}
