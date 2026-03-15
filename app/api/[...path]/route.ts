import { NextRequest, NextResponse } from 'next/server'

const BACKEND_API_URL = process.env.BACKEND_API_URL || 'http://127.0.0.1:8000'

export async function GET(request: NextRequest, { params }: { params: { path: string[] } }) {
  return handleProxy(request, 'GET', params.path)
}

export async function POST(request: NextRequest, { params }: { params: { path: string[] } }) {
  return handleProxy(request, 'POST', params.path)
}

export async function PUT(request: NextRequest, { params }: { params: { path: string[] } }) {
  return handleProxy(request, 'PUT', params.path)
}

export async function DELETE(request: NextRequest, { params }: { params: { path: string[] } }) {
  return handleProxy(request, 'DELETE', params.path)
}

export async function PATCH(request: NextRequest, { params }: { params: { path: string[] } }) {
  return handleProxy(request, 'PATCH', params.path)
}

export async function OPTIONS(request: NextRequest) {
  // Handle CORS preflight requests
  return new NextResponse(null, {
    status: 204,
    headers: {
      'Access-Control-Allow-Origin': request.headers.get('origin') || 'http://localhost:3000',
      'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, PATCH, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type, Authorization',
    },
  })
}

async function handleProxy(request: NextRequest, method: string, pathArray: string[]) {
  const path = pathArray.join('/')
  const url = new URL(request.url)
  const queryString = url.search
  
  const backendUrl = `${BACKEND_API_URL}/${path}${queryString}`
  
  try {
    // Prepare headers to forward
    const forwardHeaders: Record<string, string> = {}
    
    // Forward common headers
    const headersToForward = [
      'authorization',
      'content-type',
      'accept',
      'user-agent',
      'x-request-id'
    ]
    
    headersToForward.forEach(header => {
      const value = request.headers.get(header)
      if (value) {
        forwardHeaders[header] = value
      }
    })

    // Prepare request body
    let body: string | undefined = undefined
    if (['POST', 'PUT', 'PATCH'].includes(method)) {
      try {
        body = await request.text()
      } catch {
        // Failed to read request body
      }
    }

    // Log proxy request (server-side only)

    // Make request to backend
    const response = await fetch(backendUrl, {
      method,
      headers: forwardHeaders,
      body: body || undefined,
    })

    // Get response body
    const responseText = await response.text()
    
    // Prepare response headers
    const responseHeaders: Record<string, string> = {}
    
    // Forward response headers
    const responseHeadersToForward = [
      'content-type',
      'cache-control',
      'etag',
      'last-modified'
    ]
    
    responseHeadersToForward.forEach(header => {
      const value = response.headers.get(header)
      if (value) {
        responseHeaders[header] = value
      }
    })

    // Add CORS headers
    responseHeaders['Access-Control-Allow-Origin'] = 'http://localhost:3000'
    responseHeaders['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, PATCH, OPTIONS'
    responseHeaders['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'

    return new NextResponse(responseText, {
      status: response.status,
      statusText: response.statusText,
      headers: responseHeaders,
    })

  } catch {
    return NextResponse.json(
      { error: 'Proxy request failed' },
      { 
        status: 502,
        headers: {
          'Access-Control-Allow-Origin': 'http://localhost:3000',
          'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, PATCH, OPTIONS',
          'Access-Control-Allow-Headers': 'Content-Type, Authorization',
        }
      }
    )
  }
}
