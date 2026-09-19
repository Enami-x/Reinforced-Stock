export default function LoadingSpinner({ size = 20 }) {
  return (
    <div
      className="spinner-dual"
      style={{
        width: size,
        height: size,
        display: 'inline-block',
      }}
    />
  )
}
