import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';

const storage = new Map();
const calls = [];
const context = vm.createContext({
  sessionStorage: {getItem: k=>storage.get(k)||null, setItem:(k,v)=>storage.set(k,v), removeItem:k=>storage.delete(k)},
  Headers, URLSearchParams, FormData,
  location: {search:''},
  fetch: async(url,options)=>{
    calls.push({url,options});
    const data = url.endsWith('/auth/login')
      ? {access_token:'server-token',username:'operator01',name:'User',role:'operator'}
      : url.endsWith('/auth/me') ? {username:'operator01',name:'User',role:'operator'}
      : url.endsWith('/sites') ? [{id:'chunjeon'}]
      : {thresh_conf:.93,thresh_frames:18};
    return {ok:true,json:async()=>data};
  }
});
vm.runInContext(readFileSync('code/js/auth.js','utf8'),context);
await vm.runInContext("dgLogin('operator01','secret-password')",context);
assert.equal(calls[0].url,'/api/auth/login');
assert.equal(calls[0].options.body.get('password'),'secret-password');
assert.ok(![...storage.values()].join('').includes('secret-password'));
await vm.runInContext('dgRefresh()',context);
assert.equal(vm.runInContext('dgGetSettings().threshConf',context),.93);
assert.equal(calls.find(c=>c.url==='/api/sites').options.headers.get('Authorization'),'Bearer server-token');
await vm.runInContext('dgSaveSettings({threshConf:.93,threshFrames:18})',context);
assert.equal(calls.at(-1).options.method,'PUT');
console.log('Server authentication and settings integration OK');

context.fetch = async()=>({ok:false,status:422,json:async()=>({detail:[{loc:['body','username'],type:'string_too_short',ctx:{min_length:6}}]})});
await assert.rejects(vm.runInContext("dgApi('/auth/signup')",context),/아이디: 6자 이상/);
context.fetch = async()=>({ok:false,status:405,json:async()=>null});
await assert.rejects(vm.runInContext("dgApi('/auth/login')",context),/HTTP 405/);
context.fetch = async()=>({ok:true,json:async()=>{throw new Error('HTML');}});
await assert.rejects(vm.runInContext("dgApi('/auth/login')",context),/API 대신 웹페이지/);
context.location.protocol='file:';
await assert.rejects(vm.runInContext("dgApi('/auth/login')",context),/HTML 파일을 직접/);
console.log('Authentication validation and wrong-server errors OK');
