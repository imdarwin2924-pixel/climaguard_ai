// Shown once after creating an account: the plain temporary password is never stored, so it cannot be shown again.
export default function OneTimePassword({ name, password, signIn, reset, onDismiss }) {
  return (
    <div className="otp" role="status">
      <p><b>{reset ? `Password reset for ${name}.` : `Account created for ${name}.`}</b> Give them these details privately.
        This password is shown only once{reset ? '; their old password and open sessions no longer work' : ''}.</p>
      <p className="otp-line">Sign in with: <code>{signIn}</code></p>
      <p className="otp-line">Temporary password: <code>{password}</code></p>
      <button type="button" onClick={onDismiss}>I have passed it on</button>
    </div>
  )
}
